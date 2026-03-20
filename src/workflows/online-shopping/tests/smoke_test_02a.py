"""
Smoke test — Stage 02a (Color Verify)
Generates a solid dusty-rose test image at runtime and sends it to
qwen2.5vl:7b via Ollama to verify the vision model can assess color.
No external URLs — the test image is created in memory.
"""

import base64
import io
import os
import struct
import zlib
from pathlib import Path

from ollama import Client

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
MODEL = os.getenv("OLLAMA_VISION_MODEL", "qwen2.5vl:7b")

WORKFLOW_DIR = Path(__file__).resolve().parent.parent

# Dusty rose: muted, warm pink — RGB (188, 143, 143)
TEST_COLOR_RGB = (188, 143, 143)
TEST_COLOR_SPEC = "dusty rose — muted, warm pink, not bright or cool-toned"


def load_prompt(stage_dir: str) -> str:
    prompt_path = WORKFLOW_DIR / stage_dir / "PROMPT.md"
    return prompt_path.read_text()


def make_solid_color_png(r: int, g: int, b: int, width: int = 200, height: int = 200) -> bytes:
    """Generate a solid-color PNG using only the standard library."""

    def png_chunk(chunk_type: bytes, data: bytes) -> bytes:
        length = struct.pack(">I", len(data))
        crc = struct.pack(">I", zlib.crc32(chunk_type + data) & 0xFFFFFFFF)
        return length + chunk_type + data + crc

    # PNG signature
    signature = b"\x89PNG\r\n\x1a\n"

    # IHDR chunk
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    ihdr = png_chunk(b"IHDR", ihdr_data)

    # IDAT chunk — one row of solid color pixels, repeated
    raw_row = b"\x00" + bytes([r, g, b] * width)  # filter byte + RGB pixels
    raw_data = raw_row * height
    idat = png_chunk(b"IDAT", zlib.compress(raw_data))

    # IEND chunk
    iend = png_chunk(b"IEND", b"")

    return signature + ihdr + idat + iend


def main():
    system_prompt = load_prompt("02a-color-verify")

    user_message = (
        f"Please assess the color of the product shown in this image.\n\n"
        f"The color spec from the confirmed request is: {TEST_COLOR_SPEC}\n\n"
        f"Return your assessment in this format:\n"
        f"Color result: PASS / FAIL / AMBIGUOUS\n"
        f"Color note: [one or two sentences on what you saw and why]"
    )

    r, g, b = TEST_COLOR_RGB
    print(f"Model:      {MODEL}")
    print(f"Ollama:     {OLLAMA_BASE_URL}")
    print(f"Prompt:     {WORKFLOW_DIR / '02a-color-verify' / 'PROMPT.md'}")
    print(f"Spec:       {TEST_COLOR_SPEC}")
    print(f"Test color: RGB({r}, {g}, {b}) — solid color PNG generated in memory")
    print("-" * 60)

    png_bytes = make_solid_color_png(r, g, b)
    image_b64 = base64.b64encode(png_bytes).decode("utf-8")

    client = Client(host=OLLAMA_BASE_URL)
    response = client.chat(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": user_message,
                "images": [image_b64],
            },
        ],
    )

    print(response["message"]["content"])


if __name__ == "__main__":
    main()