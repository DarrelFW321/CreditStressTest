"""Download the Big 6 Supplementary Financial Information (SFI) packages.

Each bank's Q4 package shows the trailing five quarters, so by default this
fetches Q4 of fiscal 2018-2025 plus the latest quarter (FQ3 2026), which
covers FQ1 2018 onward. Excel is preferred; PDF is the fallback.

    python -m src.fetch_packages                  # Q4s + latest
    python -m src.fetch_packages --all-quarters   # every quarter

File names on the banks' sites change over the years, so each package has a
list of candidate URLs, tried in order. Patterns were checked in Oct 2026.
"""
import argparse
import time

import requests

from . import config

OUT = config.DATA_RAW / "banks" / "packages"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/128 Safari/537.36"}
LATEST = (2026, 3)
MONTH = {1: "january", 2: "april", 3: "july", 4: "october"}


def candidates(bank: str, y: int, q: int) -> list[str]:
    yy = f"{y % 100:02d}"
    if bank == "RY":
        base = "https://www.rbc.com/investor-relations/_assets-custom"
        # "_r" files are abridged restatements (only the changed pages); use the full package
        return [f"{base}/data/{yy}q{q}supp.xlsx", f"{base}/pdf/{yy}q{q}supp.pdf"]
    if bank == "TD":
        new = f"https://www.td.com/content/dam/tdcom/canada/about-td/pdf/quarterly-results/{y}/q{q}"
        old = f"https://www.td.com/document/PDF/investor/{y}"
        return [f"{new}/{y}-q{q}-financial-supppack-en.xlsx", f"{new}/{y}-q{q}-financial-supppack-f-en.xlsx",
                f"{old}/{y}-Q{q}_Financial_SuppPack_F_EN.xlsx", f"{new}/{y}-q{q}-financial-supppack-en.pdf",
                f"{old}/{y}-Q{q}_Financial_SuppPack_F_EN.pdf",
                f"https://www.td.com/content/dam/tdcom/canada/about-td/pdf/{y}-q{q}-financial-supppack-en.pdf"]
    if bank == "BNS":
        base = f"https://www.scotiabank.com/content/dam/scotiabank/corporate/quarterly-reports/{y}/q{q}"
        stems = [f"Q{q}{yy}_Supplementary_Financial_Information-EN", f"Q{q}{yy}_Supplementary_Financial_Information",
                 f"Q{q}{yy}-Supplementary-Financial-Information", f"Q{q}{yy}_Supplementary-Financial-Information",
                 f"Q{q}{yy}_Supplementary-Financial-Information_vF", f"{y}Q{q}-Supplementary-Financial-Information"]
        return [f"{base}/{s}.{ext}" for ext in ("xlsx", "pdf") for s in stems]
    if bank == "BMO":
        urls = []
        for host in ("https://www.prod.bmo.com", "https://www.bmo.com"):
            base = f"{host}/ir/qtrinfo/1/{y}-q{q}"
            urls += [f"{base}/Suppq{q}{yy}.xlsx", f"{base}/SuppQ{q}{yy}.xlsx",
                     f"{base}/Suppq{q}{yy}.pdf", f"{base}/SuppQ{q}{yy}.pdf"]
        return urls
    if bank == "CM":
        new = f"https://www.cibc.com/content/dam/cibc-public-assets/about-cibc/investor-relations/pdfs/quarterly-results/{y}"
        old = f"https://www.cibc.com/content/dam/about_cibc/investor_relations/pdfs/quarterly_results/{y}"
        return [f"{b}/sfi-{MONTH[q]}{yy}-en.{ext}" for b in (new, old) for ext in ("xlsx", "xls")] + \
               [f"{old}/q{q}{yy}financials-en.pdf"]
    if bank == "NBC":
        base = f"https://www.nbc.ca/content/dam/bnc/a-propos-de-nous/relations-investisseurs/resultats-trimestriels/{y}"
        return [f"{base}/suppack-q{q}-{y}-revised.xlsx", f"{base}/suppack-q{q}-{y}.xlsx",
                f"{base}/suppack-q{q}-{y}-revised.pdf", f"{base}/suppack-q{q}-{y}.pdf"]
    raise ValueError(bank)


def fetch_one(session: requests.Session, bank: str, y: int, q: int) -> str:
    dest_dir = OUT / bank
    dest_dir.mkdir(parents=True, exist_ok=True)
    existing = list(dest_dir.glob(f"{bank}_FY{y}Q{q}_SFI.*"))
    if existing:
        return f"exists  {existing[0].name}"
    for url in candidates(bank, y, q):
        try:
            r = session.get(url, timeout=60)
        except requests.RequestException:
            continue
        ctype = r.headers.get("content-type", "")
        if r.status_code == 200 and "html" not in ctype and len(r.content) > 10_000:
            ext = url.rsplit(".", 1)[-1].lower()
            path = dest_dir / f"{bank}_FY{y}Q{q}_SFI.{ext}"
            path.write_bytes(r.content)
            return f"saved   {path.name}  ({len(r.content) / 1e6:.1f} MB)  <- {url}"
        time.sleep(0.3)
    return "MISSING (download manually from the bank's IR site)"


def periods(all_quarters: bool) -> list[tuple[int, int]]:
    out = []
    for y in range(2018, LATEST[0] + 1):
        for q in range(1, 5):
            if (y, q) > LATEST:
                break
            if all_quarters or q == 4 or (y, q) == LATEST:
                out.append((y, q))
    return out


def main(all_quarters: bool = False, banks: list[str] | None = None) -> None:
    session = requests.Session()
    session.headers.update(UA)
    for bank in banks or config.BANKS:
        for y, q in periods(all_quarters):
            print(f"{bank:4} FY{y} Q{q}: {fetch_one(session, bank, y, q)}", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--all-quarters", action="store_true")
    ap.add_argument("--banks", nargs="*")
    a = ap.parse_args()
    main(a.all_quarters, a.banks)
