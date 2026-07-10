# Validation model data

These five SBML files are research validation inputs, not CMIG-authored code. They are governed by
the BiGG Models terms linked in `MODEL_SOURCES.json` and `THIRD_PARTY_NOTICES.md`; Apache-2.0 does
not apply to them.

The files are deliberately excluded from Python wheels and source distributions. Validate their
bytes before a benchmark:

```bash
python - <<'PY'
import hashlib, json, pathlib

root = pathlib.Path("models")
manifest = json.loads((root / "MODEL_SOURCES.json").read_text())
for item in manifest["models"]:
    actual = hashlib.sha256((root / item["file"]).read_bytes()).hexdigest()
    assert actual == item["sha256"], (item["file"], actual)
print("model checksums verified")
PY
```

For a publication archive, retain this manifest and cite the original reconstruction for every model
used in addition to the BiGG resource citation.
