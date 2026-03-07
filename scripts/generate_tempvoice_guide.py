"""
Generate TempVoice guide images.

900x480 dark banners with gold title and 3x3 grids.
Matches the existing dark + gold rules banner style.

Usage:
    python3 scripts/generate_tempvoice_guide.py
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# Paths
ROOT = Path(__file__).resolve().parent.parent
FONT_PATH = ROOT / "assets" / "fonts" / "Montserrat-Bold.ttf"
OUTPUT_DIR = ROOT / "assets" / "tempvoice"

# Style
BG_COLOR = (13, 13, 13)       # #0d0d0d
GOLD = (230, 184, 74)         # #E6B84A
GRAY = (156, 156, 156)        # Descriptions
CELL_BG = (24, 24, 24)        # Slightly lighter for cells
WIDTH, HEIGHT = 900, 480
LINE_HEIGHT = 2
ACCENT_W = 3                  # Gold left-border accent width

# Voice controls grid
VOICE_BUTTONS = [
    [("Lock", "Lock / unlock your channel"),
     ("Limit", "Set user limit"),
     ("Rename", "Rename channel")],
    [("Allow", "Add trusted users"),
     ("Block", "Block users"),
     ("Kick", "Kick from channel")],
    [("Claim", "Claim ownerless channel"),
     ("Transfer", "Transfer ownership"),
     ("Clear", "Clear chat messages")],
]

# Music (Boogie Bot) commands grid
MUSIC_BUTTONS = [
    [("/play", "Play a song or playlist"),
     ("/skip", "Skip to the next track"),
     ("/queue", "View the current queue")],
    [("/pause", "Pause the current track"),
     ("/resume", "Resume playback"),
     ("/stop", "Stop and disconnect")],
    [("/loop", "Set repeat mode"),
     ("/shuffle", "Shuffle the queue"),
     ("/lyrics", "Show song lyrics")],
]


def generate_grid(title: str, buttons: list, output_path: Path) -> None:
    """Generate a 900x480 guide image with a 3x3 grid."""
    img = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)

    title_font = ImageFont.truetype(str(FONT_PATH), 34)
    label_font = ImageFont.truetype(str(FONT_PATH), 20)
    desc_font = ImageFont.truetype(str(FONT_PATH), 13)

    # Centered gold title
    bbox = draw.textbbox((0, 0), title, font=title_font)
    title_w = bbox[2] - bbox[0]
    draw.text(((WIDTH - title_w) // 2, 28), title, fill=GOLD, font=title_font)

    # Thin separator line under title
    draw.rectangle([100, 78, WIDTH - 100, 79], fill=GOLD)

    # 3x3 grid
    cell_w, cell_h = 256, 105
    gap_x, gap_y = 18, 16
    total_w = 3 * cell_w + 2 * gap_x
    grid_left = (WIDTH - total_w) // 2
    grid_top = 100

    for r, row in enumerate(buttons):
        for c, (label, desc) in enumerate(row):
            x = grid_left + c * (cell_w + gap_x)
            y = grid_top + r * (cell_h + gap_y)

            # Cell background
            draw.rounded_rectangle(
                [x, y, x + cell_w, y + cell_h], radius=8, fill=CELL_BG
            )

            # Gold left accent bar
            draw.rounded_rectangle(
                [x, y, x + ACCENT_W, y + cell_h], radius=2, fill=GOLD
            )

            # Label in gold
            draw.text((x + 18, y + 20), label.upper(), fill=GOLD, font=label_font)

            # Description in gray
            draw.text((x + 18, y + 55), desc, fill=GRAY, font=desc_font)

    # Thin gold line at bottom
    draw.rectangle([0, HEIGHT - LINE_HEIGHT, WIDTH, HEIGHT], fill=GOLD)

    img.save(output_path, "PNG")
    print(f"  ✓ {output_path.relative_to(ROOT)}")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print("Generating TempVoice guides...")
    generate_grid("VOICE CONTROLS", VOICE_BUTTONS, OUTPUT_DIR / "guide.png")
    generate_grid("MUSIC COMMANDS — BOOGIE PREMIUM", MUSIC_BUTTONS, OUTPUT_DIR / "music_guide.png")
    print("Done!")


if __name__ == "__main__":
    main()
