#!/usr/bin/env python3
"""Test script for downloading a specific audiobook."""

import json
import logging
from pathlib import Path

from audible import Authenticator, Client
from audible.aescipher import decrypt_voucher_from_licenserequest

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
ASIN = "1545918686"
AUTH_FILE = Path("data/audible_auth/Christie Lyons.json")
MARKETPLACE = "us"
QUALITY = "High"

def main():
    """Download a specific audiobook for testing."""

    # Load auth
    logger.info(f"Loading auth from {AUTH_FILE}")
    auth = Authenticator.from_file(AUTH_FILE, locale=MARKETPLACE)

    # Create client
    with Client(auth=auth) as client:
        logger.info(f"Requesting license for ASIN: {ASIN}")

        # Request license
        license_response = client.post(
            f"content/{ASIN}/licenserequest",
            body={
                "drm_type": "Adrm",
                "consumption_type": "Download",
                "quality": QUALITY,
            },
        )

        # Log full response
        logger.info("=" * 80)
        logger.info("FULL LICENSE RESPONSE:")
        logger.info(json.dumps(license_response, indent=2))
        logger.info("=" * 80)

        # Check license status
        content_license = license_response.get("content_license", {})
        status_code = content_license.get("status_code")
        message = content_license.get("message")
        denial_reasons = content_license.get("license_denial_reasons", [])

        logger.info(f"Status Code: {status_code}")
        logger.info(f"Message: {message}")
        logger.info(f"Denial Reasons: {denial_reasons}")

        if status_code != "Granted":
            logger.error(f"License denied with status: {status_code}")
            if denial_reasons:
                logger.error(f"Denial reasons type: {type(denial_reasons)}")
                for i, reason in enumerate(denial_reasons):
                    logger.error(f"  Reason {i}: {reason} (type: {type(reason)})")
            return

        # Check content metadata
        content_metadata = content_license.get("content_metadata", {})
        logger.info(f"Content metadata keys: {list(content_metadata.keys())}")

        if not content_metadata:
            logger.error("Content metadata is empty!")
            return

        # Try to find download URL
        logger.info("Attempting to extract download URL...")

        # Log full content_metadata
        logger.info("=" * 80)
        logger.info("FULL CONTENT METADATA:")
        logger.info(json.dumps(content_metadata, indent=2))
        logger.info("=" * 80)

        # Try different structures
        download_url = None

        # Try 1: Standard structure
        if "content_url" in content_metadata:
            logger.info("Found 'content_url' key")
            content_url = content_metadata["content_url"]
            logger.info(f"  content_url type: {type(content_url)}")
            logger.info(f"  content_url value: {content_url}")
            if isinstance(content_url, dict) and "offline_url" in content_url:
                download_url = content_url["offline_url"]
                logger.info(f"✓ Found download URL via content_url.offline_url")

        # Try 2: Content reference
        if not download_url and "content_reference" in content_metadata:
            logger.info("Found 'content_reference' key")
            content_ref = content_metadata["content_reference"]
            logger.info(f"  content_reference type: {type(content_ref)}")
            logger.info(f"  content_reference value: {content_ref}")
            if isinstance(content_ref, dict) and "content_url" in content_ref:
                download_url = content_ref["content_url"]
                logger.info(f"✓ Found download URL via content_reference.content_url")

        # Try 3: Direct offline_url
        if not download_url and "offline_url" in content_metadata:
            download_url = content_metadata["offline_url"]
            logger.info(f"✓ Found download URL via direct offline_url")

        if download_url:
            logger.info("=" * 80)
            logger.info(f"SUCCESS! Download URL found:")
            logger.info(f"  {download_url[:100]}...")
            logger.info("=" * 80)
        else:
            logger.error("FAILED to find download URL in any expected location")
            logger.error("Available keys in content_metadata:")
            for key in content_metadata.keys():
                logger.error(f"  - {key}")

if __name__ == "__main__":
    main()
