"""Import selected, locally enrolled DhruvBrain portraits and their guide context."""
import argparse
import json
from pathlib import Path
import shutil
import tempfile


def import_faces(source, names, data):
    descriptions = {k.casefold(): v for k, v in
                    json.loads((source / "description.json").read_text(encoding="utf8")).items()}
    available = {p.stem.casefold(): p for p in (source / "known_faces").iterdir()
                 if p.suffix.lower() in {".jpg", ".jpeg", ".png"}}
    people = json.loads((data / "people.json").read_text(encoding="utf8"))
    additions = []
    for name in names:
        key = name.casefold()
        if key not in available or not isinstance(descriptions.get(key), str):
            raise ValueError(f"No portrait and description pair for {name}")
        portrait = available[key]
        additions.append(portrait)
        people[key] = {"name": portrait.stem, "image": portrait.name, "context": descriptions[key]}
    for portrait in additions:
        shutil.copy2(portrait, data / "faces" / portrait.name)
    with tempfile.NamedTemporaryFile("w", encoding="utf8", dir=data, delete=False) as tmp:
        json.dump(people, tmp, ensure_ascii=False, indent=2)
        tmp.write("\n")
    Path(tmp.name).replace(data / "people.json")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("dhruvbrain", type=Path)
    parser.add_argument("names", nargs="+")
    args = parser.parse_args()
    import_faces(args.dhruvbrain, args.names, Path(__file__).resolve().parents[1] / "data")
