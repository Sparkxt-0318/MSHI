"""22_country_check.py - compare SRDB's Country field with the country that each record's
coordinates fall in, for EVERY SRDB record with coordinates (not only those with Rs_annual).

Boundaries: Natural Earth 1:10m admin-0 map units and admin-1 states/provinces (v5.x, from
github.com/nvkelso/natural-earth-vector). Country names are normalised first (trailing spaces,
"Isreal", "Malyasia", "USA"/"United States", "UK"/"England"/"Scotland", ...; see
mshi_common.COUNTRY_ALIASES).

Status per record:
  match              point inside a map unit whose names include the stated country
  match_political    stated/actual differ only across a disputed or de facto boundary
  match_tolerance    point outside but within 10 km of the stated country (1:10m coastline and
                     border generalisation, coordinate rounding)
  no_country         Country field empty (cannot disagree; kept)
  mismatch           everything else -> flagged; excluded from modelling in Step 0

Mismatch classes, decided in this order:
  1 label_wrong (region)  the Region field names the admin-1 unit the point is in, and that
                          unit is in another country -> the coordinates agree with the Region,
                          the Country label is wrong. Fix: Country -> actual country.
  2 lon_sign / lat_sign / both_signs / swap / swap_signs
                          flipping signs and/or exchanging lat and lon puts the point inside
                          (or within 10 km of) the stated country. Fix: transformed coordinates.
  3 offshore_near         point in the sea, <= 50 km from the stated country (coastal or island
                          sites missing from 1:10m polygons, or rounding). No fix proposed.
    in_sea                point in the sea, > 50 km from the stated country.
  4 near_border           point on land in another country, <= 50 km from the stated country.
  5 label_wrong (text)    study title / Region / Site_name names the actual country (or one of
                          its admin-1 units) and not the stated one.
  6 coords_wrong          Region names an admin-1 unit of the stated country, point is far away:
                          coordinates wrong, fix not derivable.
  7 unclear
  Post-step: any class 3-7 record whose study has other records with the SAME site name that agree
  with the stated country becomes same_site_conflict, with the siblings' median coordinates as the
  proposed fix (high confidence), but only if the siblings agree within 0.1 deg; otherwise the
  class is kept and the sibling note is added to `evidence`.
Confidence:
  high    label_wrong (region) when the Region name does not also occur in the stated country;
          a sign/swap fix that lands inside the stated country AND (the Region matches the admin-1
          unit at the fixed point, OR the original point is > 100 km from the stated country and
          only one transform works)
  medium  other sign/swap fixes; label_wrong (text); coords_wrong; label_wrong (region) with an
          ambiguous Region name
  low     offshore_near, in_sea, near_border, unclear
Corroboration: another record of the same study or site name with coordinates within 0.1 deg of
the proposed fix is listed in `corroborated_by` (supporting, not required).

Usage: python -I audit/22_country_check.py
Outputs: audit/outputs/srdb_country_check.csv, audit/outputs/srdb_country_check_summary.json
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mshi_common as C  # noqa: E402

ADMIN1 = C.RAW / "naturalearth" / "ne_10m_admin_1_states_provinces.geojson"
GENERIC = {"central", "north", "south", "east", "west", "northern", "southern", "eastern", "western",
           "capital", "river", "island", "islands", "mountain", "mountains", "lake", "coast", "national",
           "region", "province", "state", "district", "county", "city", "centre", "center", "upper",
           "lower", "new", "san", "santa", "saint", "grand", "great", "little", "highland", "highlands",
           "valley", "forest", "plateau", "delta"}
STRIP_WORDS = r"\b(provinsi|propinsi|province|prefecture|state|oblast|krai|kray|county|district|" \
              r"department|departement|region|autonomous|republic|of|the|governorate|municipality|" \
              r"special|administrative|territory|federal)\b"


def admin1_names(row) -> set:
    vals = []
    for f in ["name", "name_en", "woe_name", "gn_name", "name_local"]:
        v = row.get(f)
        if isinstance(v, str) and v:
            vals.append(v)
    alt = row.get("name_alt")
    if isinstance(alt, str) and alt:
        vals += [a for a in alt.split("|") if a]
    out = set()
    for v in vals:
        n = C.norm_name(v)
        n2 = re.sub(r"\s+", " ", re.sub(STRIP_WORDS, " ", n)).strip()
        for cand in {n, n2}:
            if len(cand) >= 5 and cand not in GENERIC:
                out.add(cand)
    return out


def text_has(text: str, names: set) -> list:
    if not text:
        return []
    t = f" {text} "
    return sorted(n for n in names if f" {n} " in t)


# species / common names that contain a country name and must not count as evidence
SPECIES_PHRASES = ["norway spruce", "norway maple", "norway pine", "turkey oak", "guinea grass",
                   "guinea pig", "japanese larch", "chinese fir", "korean pine", "mongolian oak",
                   "mongolian pine", "canada goldenrod", "brazilian pepper"]
# demonyms that point to a country (used for title evidence only)
DEMONYMS = {"estonia": ["estonian"], "sweden": ["swedish"], "norway": ["norwegian"], "denmark": ["danish"],
            "finland": ["finnish"], "hungary": ["hungarian"], "slovakia": ["slovak", "slovakian"],
            "slovenia": ["slovenian", "slovene"], "china": ["chinese"], "japan": ["japanese"],
            "south korea": ["korean"], "mongolia": ["mongolian"], "germany": ["german"],
            "france": ["french"], "spain": ["spanish"], "italy": ["italian"], "canada": ["canadian"],
            "brazil": ["brazilian"], "kenya": ["kenyan"], "russia": ["russian"], "botswana": ["botswanan"],
            "malaysia": ["malaysian"], "indonesia": ["indonesian"], "namibia": ["namibian"],
            "new caledonia": ["new caledonian"], "papua new guinea": ["papua new guinean"]}


def clean_text(t: str) -> str:
    for ph in SPECIES_PHRASES:
        t = t.replace(ph, " ")
    return re.sub(r"\s+", " ", t).strip()


def with_demonyms(names: set) -> set:
    out = set(names)
    for n in names:
        out.update(DEMONYMS.get(n, []))
    return out


class Admin1:
    def __init__(self):
        import geopandas as gpd
        from shapely import STRtree
        a = gpd.read_file(ADMIN1)
        a = a[["geometry", "name", "name_en", "woe_name", "gn_name", "name_local", "name_alt", "admin"]].copy()
        a["names"] = [admin1_names(r) for _, r in a.iterrows()]
        self.a = a
        self.tree = STRtree(list(a.geometry.values))
        self.by_country = {}
        for adm, ns in zip(a["admin"], a["names"]):
            self.by_country.setdefault(C.norm_name(adm), set()).update(ns)

    def at(self, lat, lon):
        from shapely.geometry import Point
        c = self.tree.query(Point(lon, lat), predicate="intersects")
        return int(c[0]) if len(c) else None


def political_ok(stated_norm: set, unit_names: set) -> bool:
    return any(stated_norm & grp and unit_names & grp for grp in C.POLITICAL_EQUIV)


def main() -> int:
    loc = C.CountryLocator()
    units = loc.units
    adm1 = Admin1()
    d = C.load_srdb()
    studies = C.load_srdb_studies()
    title = dict(zip(studies["Study_number"], studies["Title"].astype(str)))
    has_xy = d["Latitude"].notna() & d["Longitude"].notna()
    oob = has_xy & ((d["Latitude"].abs() > 90) | (d["Longitude"].abs() > 180))
    x = d[has_xy & ~oob].copy()
    x["unit_id"] = loc.units_at(x["Latitude"].values, x["Longitude"].values)
    unit_names = units["names_norm"].tolist()
    unit_admin = [C.norm_name(v) for v in units["ADMIN"]]
    cont_unit = units["continent_ne"].tolist()

    def target_ids(kind, payload):
        if kind == "names":
            return loc.stated_unit_ids(payload)
        if kind == "continent":
            return [i for i, c in enumerate(cont_unit) if c == payload]
        return []

    def dist_target(lat, lon, kind, payload, ids):
        if abs(lat) > 90 or abs(lon) > 180:
            return np.inf
        if kind == "lat_min":
            return 0.0 if lat >= payload else np.inf
        if kind == "continent":
            u = loc.unit_at(lat, lon)
            if u is not None and loc.continent_of(lat, lon, u) == payload:
                return 0.0
            nu, km = loc.nearest_unit(lat, lon, C.TOL_KM)
            return km if (nu is not None and loc.continent_of(lat, lon, nu) == payload) else np.inf
        if not ids:
            return np.inf
        u = loc.unit_at(lat, lon)
        if u is not None and u in ids:
            return 0.0
        return loc.dist_to_units_km(lat, lon, ids)

    rows, unknown = [], {}
    for r in x.itertuples(index=False):
        lat, lon = float(r.Latitude), float(r.Longitude)
        kind, payload = C.stated_targets(r.Country)
        u = int(r.unit_id)
        land_u = u if u >= 0 else None
        unit_nm = units.iloc[u]["unit_name"] if u >= 0 else None
        if land_u is None:
            nu, _ = loc.nearest_unit(lat, lon, C.TOL_KM)
            if nu is not None:
                land_u = nu
                unit_nm = units.iloc[nu]["unit_name"] + " (coast)"
        rec = {"Record_number": r.Record_number, "Study_number": r.Study_number, "Country": r.Country,
               "Region": r.Region, "Site_name": r.Site_name, "Latitude": lat, "Longitude": lon,
               "unit_name": unit_nm, "continent_at_coords": loc.continent_of(lat, lon, land_u),
               "status": None, "mismatch_class": None, "dist_to_stated_km": np.nan, "fix_lat": np.nan,
               "fix_lon": np.nan, "fix_country": None, "fix_continent": None, "confidence": None,
               "evidence": "", "corroborated_by": ""}
        if kind == "none":
            rec["status"] = "no_country"
            rows.append(rec)
            continue
        ids = target_ids(kind, payload)
        if kind == "names" and not ids:
            unknown[str(r.Country)] = unknown.get(str(r.Country), 0) + 1
            rec["status"] = "unknown_country_name"
            rows.append(rec)
            continue
        dist = dist_target(lat, lon, kind, payload, ids)
        rec["dist_to_stated_km"] = dist
        if dist == 0.0:
            rec["status"] = "match"
            rows.append(rec)
            continue
        if kind == "names" and u >= 0 and political_ok(payload, unit_names[u]):
            rec["status"] = "match_political"
            rows.append(rec)
            continue
        if dist <= C.TOL_KM:
            rec["status"] = "match_tolerance"
            rows.append(rec)
            continue
        rec["status"] = "mismatch"

        # ---------- evidence ----------
        region_txt = C.norm_name(r.Region) if isinstance(r.Region, str) else ""
        site_txt = C.norm_name(r.Site_name) if isinstance(r.Site_name, str) else ""
        title_txt = C.norm_name(title.get(r.Study_number, ""))
        stated_admins = {unit_admin[i] for i in ids} if kind == "names" else set()
        stated_a1 = set().union(*[adm1.by_country.get(s, set()) for s in stated_admins]) if stated_admins else set()
        a1_here = adm1.at(lat, lon)
        a1_here_names = adm1.a.iloc[a1_here]["names"] if a1_here is not None else set()
        a1_here_country = C.norm_name(adm1.a.iloc[a1_here]["admin"]) if a1_here is not None else None
        reg_at_coords = text_has(region_txt, a1_here_names) if (a1_here is not None and a1_here_country not in stated_admins) else []
        reg_in_stated = text_has(region_txt, stated_a1)

        # 1. Region agrees with the point's admin-1 unit in another country -> label wrong
        if reg_at_coords and land_u is not None:
            rec["mismatch_class"] = "label_wrong"
            rec["fix_country"] = units.iloc[land_u]["unit_name"]
            rec["fix_lat"], rec["fix_lon"] = lat, lon
            rec["fix_continent"] = rec["continent_at_coords"]
            ambiguous = bool(set(reg_at_coords) & stated_a1)
            rec["confidence"] = "medium" if ambiguous else "high"
            rec["evidence"] = f"Region '{r.Region}' = admin-1 '{reg_at_coords[0]}' at the coordinates"
            rows.append(rec)
            continue

        # 2. sign / swap transforms
        cands = [("lon_sign", lat, -lon), ("lat_sign", -lat, lon), ("both_signs", -lat, -lon),
                 ("swap", lon, lat), ("swap_signs", -lon, lat), ("swap_signs", lon, -lat),
                 ("swap_signs", -lon, -lat)]
        hits = []
        for name, la, lo in cands:
            if abs(la) > 90 or abs(lo) > 180 or (la == lat and lo == lon):
                continue
            dd = dist_target(la, lo, kind, payload, ids)
            if dd <= C.TOL_KM:
                hits.append((name, la, lo, dd))
        if hits:
            name, la, lo, dd = hits[0]
            rec["mismatch_class"] = name
            rec["fix_lat"], rec["fix_lon"] = la, lo
            fu = loc.unit_at(la, lo)
            if fu is None:
                fu, _ = loc.nearest_unit(la, lo, C.TOL_KM)
            rec["fix_continent"] = loc.continent_of(la, lo, fu)
            a1_fix = adm1.at(la, lo)
            reg_at_fix = text_has(region_txt, adm1.a.iloc[a1_fix]["names"]) if a1_fix is not None else []
            unique = len({h[0] for h in hits}) == 1
            ev = []
            if reg_at_fix:
                ev.append(f"Region matches admin-1 '{reg_at_fix[0]}' at the fixed point")
            if len(hits) > 1:
                ev.append("other transforms also land in stated country: " + ",".join(sorted({h[0] for h in hits[1:]})))
            if dd == 0.0 and (reg_at_fix or (dist > 100.0 and unique)):
                rec["confidence"] = "high"
            else:
                rec["confidence"] = "medium"
            rec["evidence"] = "; ".join(ev)
            rows.append(rec)
            continue

        # 3. sea
        on_land = u >= 0
        if not on_land and land_u is None:
            rec["mismatch_class"] = "offshore_near" if dist <= C.NEAR_BORDER_KM else "in_sea"
            rec["confidence"] = "low"
            if reg_in_stated:
                rec["evidence"] = f"Region names '{reg_in_stated[0]}' in the stated country"
            rows.append(rec)
            continue
        # 4. near border
        if dist <= C.NEAR_BORDER_KM:
            rec["mismatch_class"] = "near_border"
            rec["confidence"] = "low"
            rows.append(rec)
            continue
        # 5. text evidence for the actual country: title first, then Region / Site_name
        b_admin = unit_admin[land_u] if land_u is not None else None
        b_country = with_demonyms({n for n in unit_names[land_u] if len(n) >= 4}) if land_u is not None else set()
        b_a1 = {n for n in adm1.by_country.get(b_admin, set()) if n not in GENERIC} if land_u is not None else set()
        a_country = with_demonyms(set().union(*[unit_names[i] for i in ids])) if kind == "names" else set()
        a_country = {n for n in a_country if len(n) >= 4}
        title_c = clean_text(title_txt)
        place_txt = " ".join(t for t in [region_txt, site_txt] if t)
        decided = None
        t_b, t_a = text_has(title_c, b_country | b_a1), text_has(title_c, a_country | stated_a1)
        if b_admin == "china" and "inner mongolia" in title_c:
            t_b, t_a = (t_b or ["inner mongolia"]), [h for h in t_a if h not in ("mongolia", "mongolian")]
        if t_b and not t_a:
            decided = f"title names '{t_b[0]}'"
        else:
            p_b, p_a = text_has(place_txt, b_country | b_a1), text_has(place_txt, a_country | stated_a1)
            if p_b and not p_a:
                decided = f"Region/Site_name names '{p_b[0]}'"
        if decided:
            rec["mismatch_class"] = "label_wrong"
            rec["confidence"] = "medium"
            rec["fix_country"] = units.iloc[land_u]["unit_name"]
            rec["fix_lat"], rec["fix_lon"] = lat, lon
            rec["fix_continent"] = rec["continent_at_coords"]
            rec["evidence"] = decided
            rows.append(rec)
            continue
        # 6. Region or Site_name names a unit of the stated country -> coordinates wrong
        reg_in_stated = reg_in_stated or text_has(site_txt, stated_a1)
        if reg_in_stated:
            rec["mismatch_class"] = "coords_wrong"
            rec["confidence"] = "medium"
            rec["evidence"] = f"Region names '{reg_in_stated[0]}' in the stated country"
            rows.append(rec)
            continue
        rec["mismatch_class"] = "unclear"
        rec["confidence"] = "low"
        rows.append(rec)

    res = pd.DataFrame(rows)
    # same-site siblings: a mismatch without a fix whose study has other records with the SAME site
    # name that agree with the stated country -> propose the siblings' coordinates
    ok_status = {"match", "match_tolerance", "match_political"}
    nofix = res["status"].eq("mismatch") & res["fix_lat"].isna()
    sib_pool = res[res["status"].isin(ok_status) & res["Site_name"].notna()]
    sib_groups = sib_pool.groupby(["Study_number", "Site_name"])[["Latitude", "Longitude"]]
    sib_med = sib_groups.median()
    sib_spread = (sib_groups.max() - sib_groups.min()).max(axis=1)
    sib_n = sib_groups.size()
    for i in np.nonzero(nofix.values)[0]:
        r = res.iloc[i]
        key = (r["Study_number"], r["Site_name"])
        if not isinstance(r["Site_name"], str) or key not in sib_med.index:
            continue
        la, lo = sib_med.loc[key, "Latitude"], sib_med.loc[key, "Longitude"]
        idx = res.index[i]
        note = (f"{int(sib_n.loc[key])} other record(s) of the same study and site name lie in the stated "
                f"country (spread {sib_spread.loc[key]:.2f} deg)")
        if sib_spread.loc[key] >= 0.1:
            # siblings disagree among themselves: no fix proposed, keep the class, record the note
            res.at[idx, "evidence"] = (str(r["evidence"]) + "; " if isinstance(r["evidence"], str) and r["evidence"] else "") + note
            continue
        res.at[idx, "evidence"] = f"was {r['mismatch_class']}; {note}"
        res.at[idx, "mismatch_class"] = "same_site_conflict"
        res.at[idx, "fix_lat"], res.at[idx, "fix_lon"] = la, lo
        res.at[idx, "confidence"] = "high"
        fu = loc.unit_at(la, lo)
        res.at[idx, "fix_continent"] = loc.continent_of(la, lo, fu)
    # corroboration from other records of the same study / site
    kc = res[["Record_number", "Study_number", "Site_name", "Latitude", "Longitude"]]
    for i in np.nonzero(res["fix_lat"].notna().values)[0]:
        r = res.iloc[i]
        if r["mismatch_class"] == "label_wrong":
            continue
        same = (kc["Study_number"] == r["Study_number"]).fillna(False)
        if isinstance(r["Site_name"], str) and r["Site_name"]:
            same |= (kc["Site_name"] == r["Site_name"]).fillna(False)
        same &= kc["Record_number"] != r["Record_number"]
        s = kc[same]
        near = s[(np.abs(s["Latitude"] - r["fix_lat"]) < 0.1) & (np.abs(s["Longitude"] - r["fix_lon"]) < 0.1)]
        if len(near):
            res.at[res.index[i], "corroborated_by"] = ";".join(str(int(v)) for v in near["Record_number"].head(5))
    keep = d[["Record_number", "Rs_annual", "Manipulation", "Quality_flag", "Annual_coverage",
              "Study_midyear", "Ecosystem_type", "Meas_method"]]
    res = res.merge(keep, on="Record_number", how="left")
    res.to_csv(C.OUT / "srdb_country_check.csv", index=False)

    mm = res[res.status == "mismatch"]
    summ = {
        "created": C.now_utc(), "srdb_commit": "02163a7",
        "natural_earth": ["ne_10m_admin_0_map_units.geojson", "ne_10m_admin_1_states_provinces.geojson"],
        "n_records_total": int(len(d)), "n_without_coordinates": int((~has_xy).sum()),
        "n_out_of_bounds": int(oob.sum()), "n_checked": int(len(res)),
        "status_counts": res["status"].value_counts().to_dict(),
        "mismatch_class_counts": mm["mismatch_class"].value_counts().to_dict(),
        "mismatch_confidence_counts": mm["confidence"].value_counts().to_dict(),
        "mismatch_studies": int(mm["Study_number"].nunique()),
        "mismatch_with_rs_annual": int(mm["Rs_annual"].notna().sum()),
        "class_by_confidence": mm.groupby(["mismatch_class", "confidence"]).size().rename("n").reset_index().to_dict("records"),
        "unknown_country_names": unknown, "tolerance_km": C.TOL_KM, "near_border_km": C.NEAR_BORDER_KM,
    }
    C.write_json(summ, C.OUT / "srdb_country_check_summary.json")
    for k in ["n_checked", "status_counts", "mismatch_class_counts", "mismatch_confidence_counts",
              "mismatch_studies", "mismatch_with_rs_annual", "unknown_country_names"]:
        print(k, summ[k])
    chk = res[res["Record_number"].isin([13585, 13587, 10578, 9842, 5458, 6611])]
    print(chk[["Record_number", "Country", "Region", "Latitude", "Longitude", "unit_name", "mismatch_class",
               "fix_lat", "fix_lon", "fix_country", "confidence"]].to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
