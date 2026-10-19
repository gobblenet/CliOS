"""Crée un paquet de style CliOS à partir du gabarit officiel."""

import argparse
import json
import re
import shutil
from pathlib import Path


STYLE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


def main():
    parser = argparse.ArgumentParser(description="Create a new CliOS style")
    parser.add_argument("style_id", help="Folder identifier, e.g. racing_blue")
    parser.add_argument("label", help="Display label, e.g. Racing Blue")
    args = parser.parse_args()

    if not STYLE_ID_PATTERN.fullmatch(args.style_id):
        parser.error("style_id must use only a-z, 0-9 and _, and start with a letter")

    project_root = Path(__file__).resolve().parent.parent
    styles_dir = project_root / "frontend" / "styles"
    target_root = project_root / "frontend" / "dev_styles"
    target_root.mkdir(parents=True, exist_ok=True)
    template_dir = styles_dir / "_template"
    target_dir = target_root / args.style_id
    if target_dir.exists():
        parser.error(f"the style already exists: {target_dir}")

    shutil.copytree(template_dir, target_dir)
    manifest_path = target_dir / "style.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["id"] = args.style_id
    manifest["label"] = args.label
    manifest_path.write_text(json.dumps(manifest, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")
    print(target_dir)


if __name__ == "__main__":
    main()
