#!/usr/bin/env python3
"""Apply the build settings the app cannot work without.

1. `applicationId` must be the agreed identifier, not the templated package name.
2. `minSdk` is 24 (Android 7): below that the device SQLite build is too old to run the
   client views reliably.
3. `noCompress "sqlite"` keeps the 65 MB bundle as a plain file. Without it AAPT compresses
   the asset and sqflite cannot open it from the APK.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


def patch(path: Path, application_id: str) -> None:
    text = path.read_text(encoding="utf-8")
    original = text

    text = re.sub(
        r'applicationId\s*=\s*"[^"]+"',
        f'applicationId = "{application_id}"',
        text,
        count=1,
    )
    text = re.sub(
        r'applicationId\s+"[^"]+"',
        f'applicationId "{application_id}"',
        text,
        count=1,
    )
    text = re.sub(r'minSdk\s*=\s*flutter\.minSdkVersion', 'minSdk = 24', text)
    text = re.sub(r'minSdkVersion\s+flutter\.minSdkVersion', 'minSdkVersion 24', text)
    text = re.sub(r'minSdk\s*=\s*\d+', 'minSdk = 24', text)
    text = re.sub(r'minSdkVersion\s+\d+', 'minSdkVersion 24', text)

    if 'noCompress' not in text:
        if path.suffix == '.kts':
            text = text.replace(
                '    android {',
                '    androidResources {\n        noCompress += "sqlite"\n    }\n\n    android {',
                1,
            )
        else:
            text = text.replace(
                '    android {',
                "    aaptOptions {\n        noCompress 'sqlite'\n    }\n\n    android {",
                1,
            )

    if text == original:
        raise SystemExit(f"nothing was patched in {path}; inspect the template manually")

    path.write_text(text, encoding="utf-8")
    checks = {
        'applicationId': 'application_id' if application_id in text else 'MISSING',
        'minSdk 24': 'yes' if ('minSdk = 24' in text or 'minSdkVersion 24' in text) else 'MISSING',
        'noCompress sqlite': 'yes' if 'noCompress' in text else 'MISSING',
    }
    print(f"patched {path.name}: {checks}")


def main(argv: list[str]) -> int:
    app_dir = Path(argv[1]).resolve()
    application_id = argv[2]
    candidates = [
        app_dir / "android" / "app" / "build.gradle.kts",
        app_dir / "android" / "app" / "build.gradle",
    ]
    target = next((path for path in candidates if path.is_file()), None)
    if target is None:
        raise SystemExit(f"no app build.gradle found under {app_dir}/android/app")
    patch(target, application_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
