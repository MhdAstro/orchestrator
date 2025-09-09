import httpx
import asyncio
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from ..schemas.telegram_webhook import TelegramWebhookPayload

# --- Logging Configuration ---
# This sets up a standard logger to print messages with timestamps and severity levels.
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Router Initialization ---
router = APIRouter()

# --- External Service URLs ---
# Replace these with the actual URLs of your services.
SMART_UPLOADER_URL = "https://smart-uploader.basalam.dev/process-images"
VIDEO_CHECK_URL = "https://dwh-n8n.basalam.dev/webhook-test/Video-Check"
DESCRIPTION_SERVICE_URL = "https://request-maker.basalam.dev/api/v1/generate-description" # <-- IMPORTANT: Update this URL
BASALAM_USER_INFO_URL = "https://core.basalam.com/v3/users/me"
BASALAM_PRODUCTS_URL_TEMPLATE = "https://core.basalam.com/v3/vendors/{vendor_id}/products"

# --- HTTP Client Dependency ---
async def get_http_client():
    """Provides an httpx.AsyncClient for making API calls."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        yield client

# --- Main Orchestrator Endpoint ---
@router.post(
    "/products/create_from_webhook",
    summary="Create a product by orchestrating multiple services"
)
async def create_product_from_webhook(
    payload: TelegramWebhookPayload,
    client: httpx.AsyncClient = Depends(get_http_client)
):
    """
    This endpoint orchestrates the entire product creation workflow:
    1.  Receives a raw webhook payload.
    2.  Calls media processing services (images and video).
    3.  Calls the description service to generate a base product payload.
    4.  Injects media IDs into the payload with the correct format.
    5.  Submits the final, complete payload to the Basalam API.
    """
    # --- Step 1: Extract Data from Incoming Payload ---
    logger.info("Orchestration started for a new product.")
    description = payload.raw_data_json.raw_message.message
    photo_links = [str(p) for p in payload.raw_data_json.photos]
    video_link = str(payload.raw_data_json.video) if payload.raw_data_json.video else None
    stock = payload.raw_data_json.stock
    access_token = payload.access_token
    
    # --- Step 1.5: Get User Info and Vendor ID ---
    try:
        logger.info(f"Getting user info from Basalam API at: {BASALAM_USER_INFO_URL}")
        headers = {"Authorization": f"Bearer {access_token}"}
        user_info_response = await client.get(BASALAM_USER_INFO_URL, headers=headers)
        logger.info(f"User info API responded with status: {user_info_response.status_code}")
        user_info_response.raise_for_status()
        
        user_data = user_info_response.json()
        vendor_id = user_data.get("vendor", {}).get("id")
        
        if not vendor_id:
            logger.error("User does not have a vendor account or vendor ID is missing.")
            raise HTTPException(status_code=400, detail="User does not have a valid vendor account.")
        
        logger.info(f"Successfully retrieved vendor_id: {vendor_id}")
        basalam_final_url = BASALAM_PRODUCTS_URL_TEMPLATE.format(vendor_id=vendor_id)
        
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error from Basalam user info API: Status {e.response.status_code} - Response: {e.response.text}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Authentication failed: {e.response.text}")

    # --- Step 2: Process Media (Images and Video Concurrently) ---
    try:
        tasks = []
        task_urls = []
        logger.info(f"Calling Image Uploader for {len(photo_links)} photos at: {SMART_UPLOADER_URL}")
        tasks.append(client.post(SMART_UPLOADER_URL, json={"photo_links": photo_links}))
        task_urls.append(SMART_UPLOADER_URL)

        video_task_present = False
        if video_link:
            video_task_present = True
            logger.info(f"Calling Video Checker at: {VIDEO_CHECK_URL}")
            tasks.append(client.post(VIDEO_CHECK_URL, json={"video-link": video_link}))
            task_urls.append(VIDEO_CHECK_URL)
        else:
            logger.info("No video link provided, skipping video check.")

        responses = await asyncio.gather(*tasks, return_exceptions=True)

        for i, res in enumerate(responses):
            if isinstance(res, Exception):
                failed_url = task_urls[i]
                logger.error(f"Network error while calling {failed_url}: {res}")
                raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=f"Network error for {failed_url}")

        image_response = responses[0]
        logger.info(f"Image Uploader responded with status: {image_response.status_code}")
        logger.info(f"Image Uploader RAW RESPONSE BODY: {image_response.text}") # For debugging
        image_response.raise_for_status()
        processed_images = image_response.json().get("processed_images", [])
        image_ids = [img['id'] for img in processed_images if 'id' in img]
        
        if not image_ids:
            logger.warning("Image Uploader returned no valid image IDs.")
            raise HTTPException(status_code=400, detail="Uploader service returned no valid image IDs.")
        logger.info(f"Successfully processed {len(image_ids)} image IDs.")

        video_id = None
        if video_task_present:
            video_response = responses[1]
            logger.info(f"Video Checker responded with status: {video_response.status_code}")
            video_response.raise_for_status()
            if not video_response.json().get("is_forbidden"):
                video_id = video_response.json().get("id")
                logger.info(f"Video is not forbidden. Video ID: {video_id}")
            else:
                logger.warning("Video was marked as forbidden by the checking service.")

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error from a media service {e.request.url}: Status {e.response.status_code} - Response: {e.response.text}")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Error from media service {e.request.url}: {e.response.text}")

    # --- Step 3: Prepare Final Payload with Description Service ---
    try:
        new_service_payload = {"raw_text": description}
        logger.info(f"Calling Description Service at: {DESCRIPTION_SERVICE_URL}")
        prep_response = await client.post(DESCRIPTION_SERVICE_URL, json=new_service_payload)
        logger.info(f"Description Service responded with status: {prep_response.status_code}")
        prep_response.raise_for_status()

        basalam_ready_payload = prep_response.json().get("data")
        if not basalam_ready_payload:
            logger.error("Description service responded successfully but the 'data' key was missing or empty.")
            raise HTTPException(status_code=500, detail="Received invalid payload from description service.")
        
        logger.info("Successfully prepared base payload from Description Service.")

        # --- Step 4: Inject Media IDs with the Correct Format for Basalam API ---
        if image_ids:
            basalam_ready_payload["photo"] = image_ids[0]      # First image is the main photo
            basalam_ready_payload["photos"] = image_ids[1:]    # The rest are other photos
        
        if video_id:
            basalam_ready_payload["video"] = video_id          # Use the correct key "video"

        basalam_ready_payload["vendor_id"] = vendor_id
        basalam_ready_payload["preparation_days"] = 1
        basalam_ready_payload["stock"] = stock
        basalam_ready_payload["unit_type"] = 6304 # Example ID for "عدد"
        basalam_ready_payload["unit_quantity"] = 1

        logger.info("Final payload is ready to be sent to Basalam.")
        
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error from Description service: Status {e.response.status_code} - Response: {e.response.text}")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Error from Description service: {e.response.text}")

    # --- Step 5: Final Submission to Basalam ---
    try:
        logger.info(f"Submitting final payload to Basalam API at: {basalam_final_url}")
        # Use the access token from the payload for authentication
        headers = {"Authorization": f"Bearer {access_token}"}
        final_response = await client.post(basalam_final_url, json=basalam_ready_payload, headers=headers)
        logger.info(f"Basalam API responded with status: {final_response.status_code}")
        final_response.raise_for_status()
        
        logger.info("Orchestration completed and product submitted successfully!")
        return {
            "status": "success",
            "message": "Product orchestrated and submitted successfully.",
            "submitted_payload": basalam_ready_payload,
            "basalam_response": final_response.json()
        }
        
    except httpx.HTTPStatusError as e:
        logger.error(f"Final submission to Basalam API failed: Status {e.response.status_code} - Response: {e.response.text}")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Final submission to Basalam API failed: {e.response.text}")