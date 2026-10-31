# Third-party notices

This file must ship with any distributed database or application bundle, because the merged data is
a derivative of the projects below. It is generated from `config/sources.yaml` and the
`data_sources` table, so the shipped database always states its own obligations.

## OBDex

* Repository: <https://github.com/foerbsnavi/OBDex>
* Code licence: MIT · Data licence: **CC0-1.0** (<https://creativecommons.org/publicdomain/zero/1.0/>)
* Used for: generic DTC titles/descriptions (EN/DE), components, causes with likelihood, symptoms,
  repair effort, flags, related codes, parameter definitions
* Attribution not legally required; recorded anyway.

## Wal33D dtc-database

* Repository: <https://github.com/Wal33D/dtc-database>
* Licence: **MIT** (code and data)
* Copyright (c) the Wal33D dtc-database contributors
* Used for: generic and manufacturer-specific DTC descriptions (EN)
* MIT notice and permission text must accompany any substantial portion of this data.

## autodiag2/database

* Repository: <https://github.com/autodiag2/database>
* Code licence: GPL-3.0-or-later (not used — this project contains no code from that repository)
* Data licence: **ODbL-1.0** (database) / **DbCL-1.0** (contents)
* Used for: DTC definitions with brand/ECU context, protocol and standard, evidence
* Share-alike: a publicly distributed derivative database must be offered under ODbL terms.
* Status in this project: **legal review pending** (see `docs/LICENSES.md`).

## OBDb

* Organisation: <https://github.com/OBDb> (one repository per vehicle)
* Licence: **CC-BY-SA-4.0** (per repository)
* Used for: vehicle generations and model years, ECU/CAN headers, Mode 21/22 parameter definitions
* Share-alike and attribution required.
* Status in this project: **legal review pending**.

## Data not included

Nothing is imported from sources whose licence is unclear or that forbid redistribution. A source
without a licence record in `config/sources.yaml` cannot be imported at all.

---

Engine code: MIT — see [`LICENSE`](LICENSE).
