from __future__ import annotations

from functools import lru_cache

import pandas as pd

from company_links_db import get_company_official_industry_df


@lru_cache(maxsize=1)
def load_official_industry_lookup():
    mapping_df = get_company_official_industry_df()
    if mapping_df.empty:
        return {}
    return dict(zip(mapping_df["code"], mapping_df["industry"]))


def fill_missing_industry(source_df, code_column="code", industry_column="industry"):
    if source_df.empty or code_column not in source_df.columns:
        return source_df

    result_df = source_df.copy()
    result_df[code_column] = result_df[code_column].astype(str).str.zfill(4)
    if industry_column not in result_df.columns:
        result_df[industry_column] = None

    result_df[industry_column] = result_df[industry_column].fillna("").astype(str).str.strip()
    missing_mask = result_df[industry_column] == ""
    if missing_mask.any():
        industry_lookup = load_official_industry_lookup()
        result_df.loc[missing_mask, industry_column] = (
            result_df.loc[missing_mask, code_column].map(industry_lookup).fillna("")
        )
    result_df[industry_column] = result_df[industry_column].replace("", None)
    return result_df
