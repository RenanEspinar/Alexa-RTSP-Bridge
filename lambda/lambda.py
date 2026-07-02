"""
Alexa RTSP Bridge - AWS Lambda Smart Home Proxy

This Lambda function forwards Alexa Smart Home directives to Home Assistant.
For camera stream responses, it replaces the Home Assistant-generated HLS URL
with an externally generated Alexa-compatible HLS URL.

Repository: Alexa RTSP Bridge
"""

import json
import logging
import os
import time

import urllib3


DEBUG = bool(os.environ.get("DEBUG"))

LOGGER = logging.getLogger("Alexa-RTSP-Bridge")
LOGGER.setLevel(logging.DEBUG if DEBUG else logging.INFO)

CAMERA_RESPONSE_DELAY_SECONDS = float(
    os.environ.get("CAMERA_RESPONSE_DELAY_SECONDS", "1")
)

ALEXA_HLS_URLS = {
    "camera#solario": "https://alexa-hls.example.com/solario/index.m3u8",
    "camera#jardin": "https://alexa-hls.example.com/jardin/index.m3u8",
    "camera#pasillo": "https://alexa-hls.example.com/pasillo/index.m3u8",
    "camera#estacionamiento": "https://alexa-hls.example.com/estacionamiento/index.m3u8",
    "camera#calle_kantutas_a": "https://alexa-hls.example.com/calle_kantutas_a/index.m3u8",
    "camera#calle_kantutas_b": "https://alexa-hls.example.com/calle_kantutas_b/index.m3u8",
}


def is_camera_stream_response(response_json):
    try:
        header = response_json.get("event", {}).get("header", {})
        return (
            header.get("namespace") == "Alexa.CameraStreamController"
            and header.get("name") == "Response"
        )
    except Exception:
        return False


def build_error_response(message_id, error_type, message):
    return {
        "event": {
            "header": {
                "namespace": "Alexa",
                "name": "ErrorResponse",
                "messageId": message_id or "error-message",
                "payloadVersion": "3",
            },
            "payload": {
                "type": error_type,
                "message": message,
            },
        }
    }


def adjust_camera_stream_response(response_json):
    if not is_camera_stream_response(response_json):
        return response_json

    try:
        event = response_json.get("event", {})
        payload = event.get("payload", {})
        endpoint = event.get("endpoint", {})
        endpoint_id = endpoint.get("endpointId")

        hls_uri = ALEXA_HLS_URLS.get(endpoint_id)

        if not hls_uri:
            LOGGER.warning("No HLS URL mapping found for endpointId: %s", endpoint_id)
            return response_json

        camera_streams = payload.get("cameraStreams", [])

        for stream in camera_streams:
            old_uri = stream.get("uri")

            stream["uri"] = hls_uri
            stream["protocol"] = "HLS"
            stream["authorizationType"] = "NONE"
            stream["videoCodec"] = "H264"
            stream["audioCodec"] = "NONE"
            stream["resolution"] = {
                "width": 960,
                "height": 540,
            }

            LOGGER.info("Camera endpointId: %s", endpoint_id)
            LOGGER.info("Old Home Assistant stream URI: %s", old_uri)
            LOGGER.info("New Alexa-compatible HLS URI: %s", hls_uri)

    except Exception as exc:
        LOGGER.error("Error adjusting camera stream response: %s", exc)

    return response_json


def lambda_handler(event, context):
    LOGGER.info("========== ALEXA DIRECTIVE RECEIVED ==========")
    LOGGER.info(json.dumps(event, indent=2))

    base_url = os.environ.get("BASE_URL")
    if not base_url:
        return build_error_response(
            None,
            "INTERNAL_ERROR",
            "BASE_URL environment variable is not configured",
        )

    base_url = base_url.strip("/")

    directive = event.get("directive")
    if not directive:
        return build_error_response(
            None,
            "INVALID_DIRECTIVE",
            "Malformed request: missing directive",
        )

    header = directive.get("header", {})
    message_id = header.get("messageId", "error-message")
    payload_version = header.get("payloadVersion")

    LOGGER.info("Namespace: %s", header.get("namespace"))
    LOGGER.info("Name: %s", header.get("name"))
    LOGGER.info("Payload version: %s", payload_version)

    if payload_version != "3":
        return build_error_response(
            message_id,
            "INVALID_DIRECTIVE",
            "Only payloadVersion 3 is supported",
        )

    scope = directive.get("endpoint", {}).get("scope")

    if scope is None:
        scope = directive.get("payload", {}).get("grantee")

    if scope is None:
        scope = directive.get("payload", {}).get("scope")

    if not scope:
        return build_error_response(
            message_id,
            "INVALID_DIRECTIVE",
            "Malformed request: missing BearerToken scope",
        )

    if scope.get("type") != "BearerToken":
        return build_error_response(
            message_id,
            "INVALID_DIRECTIVE",
            "Only BearerToken scope is supported",
        )

    token = scope.get("token")

    if not token and DEBUG:
        token = os.environ.get("LONG_LIVED_ACCESS_TOKEN")

    if not token:
        return build_error_response(
            message_id,
            "INVALID_AUTHORIZATION_CREDENTIAL",
            "Missing bearer token",
        )

    verify_ssl = not bool(os.environ.get("NOT_VERIFY_SSL"))

    http = urllib3.PoolManager(
        cert_reqs="CERT_REQUIRED" if verify_ssl else "CERT_NONE",
        timeout=urllib3.Timeout(connect=2.0, read=10.0),
    )

    ha_url = f"{base_url}/api/alexa/smart_home"

    LOGGER.info("Forwarding directive to Home Assistant: %s", ha_url)

    response = http.request(
        "POST",
        ha_url,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        body=json.dumps(event).encode("utf-8"),
    )

    ha_response_text = response.data.decode("utf-8")

    LOGGER.info("========== HOME ASSISTANT RAW RESPONSE ==========")
    LOGGER.info("HTTP Status: %s", response.status)
    LOGGER.info(ha_response_text)

    if response.status >= 400:
        error_type = (
            "INVALID_AUTHORIZATION_CREDENTIAL"
            if response.status in (401, 403)
            else "INTERNAL_ERROR"
        )

        return build_error_response(message_id, error_type, ha_response_text)

    try:
        parsed_response = json.loads(ha_response_text)
    except json.JSONDecodeError:
        return build_error_response(
            message_id,
            "INTERNAL_ERROR",
            "Home Assistant response is not valid JSON",
        )

    parsed_response = adjust_camera_stream_response(parsed_response)

    if is_camera_stream_response(parsed_response):
        LOGGER.info(
            "Waiting %.1f seconds before returning camera stream to Alexa",
            CAMERA_RESPONSE_DELAY_SECONDS,
        )
        time.sleep(CAMERA_RESPONSE_DELAY_SECONDS)

    LOGGER.info("========== RETURNING RESPONSE TO ALEXA ==========")
    LOGGER.info(json.dumps(parsed_response, indent=2))

    return parsed_response
