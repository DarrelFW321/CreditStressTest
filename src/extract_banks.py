"""Fill data/raw/banks/pcl_loans.csv and capital.csv from the downloaded SFI packages.

    python -m src.extract_banks            # all banks with an extractor
    python -m src.extract_banks RY TD      # selected banks

Rows for the extracted banks are replaced; rows for other banks (e.g. typed in
by hand from PDF-only packages) are kept.
"""
import sys

import pandas as pd

from . import config
from .extract import bmo, bns, cibc, nbc, rbc, td
from .load_banks import CAPITAL_FILE, PCL_FILE

PACKAGES = config.DATA_RAW / "banks" / "packages"
EXTRACTORS = {"RY": rbc.extract, "CM": cibc.extract, "TD": td.extract, "BNS": bns.extract, "NBC": nbc.extract, "BMO": bmo.extract}


def _replace(path, new: pd.DataFrame, banks: list[str]) -> None:
    old = pd.read_csv(path, keep_default_na=False, na_values=[""])
    old = old[~old["bank"].isin(banks)]
    out = pd.concat([old, new[old.columns.intersection(new.columns).tolist() or new.columns]], ignore_index=True)
    out.sort_values(["bank", "fiscal_year", "fiscal_quarter"]).to_csv(path, index=False)


def main(banks: list[str]) -> None:
    for bank in banks:
        pcl, cap = EXTRACTORS[bank](PACKAGES / bank)
        _replace(PCL_FILE, pcl, [bank])
        _replace(CAPITAL_FILE, cap, [bank])
        q = cap[["fiscal_year", "fiscal_quarter"]].apply(tuple, axis=1)
        print(f"{bank}: {len(pcl)} PCL/loan rows, {len(cap)} capital rows, FQ{q.min()[1]} {q.min()[0]} "
              f"to FQ{q.max()[1]} {q.max()[0]}")


if __name__ == "__main__":
    main(sys.argv[1:] or list(EXTRACTORS))
