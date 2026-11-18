# DAxxv Rail Data

Public, validated timetable snapshots for DAxxv Rail Locator. **ProRail synchronization remains separate** and is not modified by this repository.

- Source: `https://gtfs.ovapi.nl/openov-nl/gtfs-openov-nl.zip`
- Filtered Arriva routes: RS11 (Maaslijn), RS12, RS15, RS18, RE18.
- Checks: ZIP integrity, required GTFS tables, required lines and trips, checksum.
- Schedule: 05:00 and 07:00 Europe/Amsterdam (GitHub may delay scheduled jobs).
- Only changed regional data are published. Existing valid data remain active if a run fails.

## First run

1. Add `scripts/build_gtfs.py` and `.github/workflows/update-ovapi.yml` to this repository.
2. From the **Actions** tab, choose **Actualizare OVapi Arriva** and click **Run workflow** (branch main).
3. After the workflow succeeds, verify `data/manifest.json` points to an accessible immutable ZIP in Releases.
4. Then modify Android **Arriva** sync to read the manifest, download only when SHA-256 changes, validate and import atomically. Leave **ProRail** sync untouched.

Expected manifest URL after the first successful run:

`https://raw.githubusercontent.com/danielgogoneata-ui/DAxxv-Rail-Data/main/data/manifest.json`

No Android code is changed by uploading these files. This is timetable data, not live dispatch or operational safety instructions.
