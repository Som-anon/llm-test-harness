import base64
from pathlib import Path


def image_to_data_uri(image_path):
    """Encode an image file as a base64 data URI suitable for vision models."""
    p = Path(image_path)
    mime = "image/jpeg" if p.suffix.lower() in (".jpg", ".jpeg") else "image/png"
    data = base64.b64encode(p.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{data}"


def build_image_messages(test):
    """Build the messages list for an image-based test.

    The test dict may contain an ``image`` key with a ``path`` field.
    The user message content is turned into a list of content parts:
    an image_url part followed by the text prompt.
    """
    image_cfg = test.get("image", {})
    image_path = image_cfg.get("path")
    if not image_path:
        raise ValueError("Image test is missing 'image.path'")

    data_uri = image_to_data_uri(image_path)

    req = test.get("request", {})
    messages = req.get("messages", [])

    # Inject the image into the first user message as a content part list.
    for msg in messages:
        if msg.get("role") == "user":
            text = msg.get("content", "")
            if isinstance(text, str):
                msg["content"] = [
                    {"type": "text", "text": text},
                    {"type": "image_url", "image_url": {"url": data_uri}},
                ]
            break

    return messages
