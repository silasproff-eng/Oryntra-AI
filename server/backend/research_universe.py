from __future__ import annotations

import random
import re
from typing import Iterable


BROAD_US_LIQUID_UNIVERSE = [
    "A", "AA", "AAP", "ACGL", "ACN", "ADP", "ADSK", "AEE", "AES", "AFL",
    "AFRM", "AJG", "AKAM", "ALB", "ALGN", "ALL", "ALLY", "ALNY", "AMCR", "AMP",
    "ANET", "APA", "APD", "APO", "APP", "APTV", "ARE", "ARES", "ARM", "ASML",
    "ASTS", "AVB", "AVY", "AXON", "BALL", "BAX", "BBY", "BDX", "BE", "BEN",
    "BF.B", "BIDU", "BIIB", "BILI", "BIO", "BKNG", "BMRN", "BRO", "BROS", "BWA",
    "CARR", "CAVA", "CB", "CBOE", "CBRE", "CCI", "CCL", "CDNS", "CDW", "CE",
    "CEG", "CELH", "CF", "CHD", "CHRW", "CHTR", "CINF", "CLF", "CLS", "CLX",
    "CMA", "CNC", "CNP", "CPNG", "CPRT", "CPT", "CRL", "CSGP", "CTAS", "CTRA",
    "CTVA", "CVNA", "DHI", "DKNG", "DLR", "DOCU", "DOV", "DOW", "DPZ", "DRI",
    "DTE", "DUOL", "DXCM", "EA", "EBAY", "ECL", "EDR", "EFX", "EIX", "ELF",
    "ENPH", "EQR", "EQT", "ES", "ESS", "EW", "EXPD", "EXPE", "F", "FAST",
    "FCX", "FERG", "FI", "FICO", "FIS", "FITB", "FIVE", "FLEX", "FOX", "FOXA",
    "FSLR", "FTNT", "GDDY", "GEN", "GEV", "GM", "GPC", "GPN", "GRMN", "HAS",
    "HBAN", "HCA", "HEI", "HLT", "HIMS", "HOLX", "HPE", "HPQ", "HRL", "HSIC",
    "HST", "HSY", "HUBB", "HWM", "IBKR", "IBM", "IDXX", "IEX", "IFF", "ILMN",
    "INCY", "IONQ", "IP", "IPG", "IQV", "IR", "IT", "ITW", "IVZ", "J",
    "JBHT", "JBL", "JCI", "K", "KEY", "KEYS", "KHC", "KIM", "KKR", "KMX",
    "KVUE", "LDOS", "LEN", "LH", "LI", "LKQ", "LNC", "LNT", "LVS", "LW",
    "LYB", "LYV", "MAR", "MARA", "MAS", "MCK", "MELI", "MKC", "MKTX", "MO",
    "MOS", "MPWR", "MSCI", "MSI", "NCLH", "NDAQ", "NEM", "NIO", "NOMD", "NRG",
    "NTAP", "NTRS", "NU", "NUE", "O", "ODFL", "OKE", "OKLO", "OMC", "ON",
    "ONON", "OTIS", "OWL", "PATH", "PAYC", "PAYX", "PCAR", "PCG", "PDD", "PH",
    "PHM", "PINS", "PKG", "POOL", "PPG", "PPL", "PRU", "PSA", "PTC", "PWR",
    "RBLX", "RF", "RHI", "RIVN", "RJF", "RKLB", "RMD", "ROK", "ROKU", "ROL",
    "ROP", "SE", "SJM", "SNA", "SNAP", "SNPS", "STLD", "STT", "STX", "SWK",
    "SWKS", "TAP", "TDG", "TDY", "TECH", "TEL", "TER", "TMUS", "TOST", "TPR",
    "TROW", "TSM", "TT", "TTD", "TTWO", "TXT", "UDR", "UHS", "ULTA", "UPST",
    "VLO", "VMC", "VRSK", "VRSN", "VST", "VTR", "VTRS", "WAB", "WAT", "WBD",
    "WELL", "WY", "WYNN", "XPEV", "XYL", "XYZ", "ZBRA", "ZTS", "ACM", "ADC",
    "AGCO", "ALGM", "ATI", "BILL", "BURL", "BWXT", "CACI", "CCJ", "CHWY", "COTY",
    "CRDO", "CUBE", "CW", "CYBR", "DAR", "DAY", "DOC", "DT", "DTM", "ELF",
    "EME", "ENTG", "ESTC", "EVR", "EXAS", "FIX", "FND", "FN", "FRPT", "GTLB",
    "GWRE", "HALO", "IOT", "JEF", "LITE", "MANH", "MNDY", "MORN", "MTCH",
    "NTRA", "NVT", "OKTA", "OLED", "ONTO", "OSK", "PCTY", "PODD", "PSTG",
    "RBRK", "RELY", "SAIA", "SFM", "SMCI", "SOFI", "SOUN", "SPOT", "SRAD",
    "TEM", "TOL", "TWLO", "U", "VEEV", "WDC", "WIX", "WSM", "YETI", "ZI",
]


def clean_tickers(values: Iterable[str], max_count: int = 500) -> tuple[list[str], list[str]]:
    cleaned: list[str] = []
    rejected: list[str] = []
    seen: set[str] = set()
    for raw in values or []:
        ticker = str(raw or "").strip().upper().replace(" ", "")
        if not ticker or not re.fullmatch(r"[A-Z0-9][A-Z0-9.-]{0,11}", ticker):
            if str(raw or "").strip():
                rejected.append(str(raw))
            continue
        if ticker not in seen:
            cleaned.append(ticker)
            seen.add(ticker)
        if len(cleaned) >= max(1, min(int(max_count), 500)):
            break
    return cleaned, rejected


def select_unseen_tickers(
    cached_tickers: Iterable[str],
    *,
    count: int = 150,
    seed: int = 73021,
    additional_exclusions: Iterable[str] | None = None,
) -> list[str]:
    excluded = {str(ticker).strip().upper() for ticker in cached_tickers or []}
    excluded.update(str(ticker).strip().upper() for ticker in additional_exclusions or [])
    
    candidates, _ = clean_tickers(BROAD_US_LIQUID_UNIVERSE, max_count=500)
    candidates = [ticker for ticker in candidates if ticker not in excluded]
    
    rng = random.Random(int(seed))
    rng.shuffle(candidates)
    
    requested = max(1, min(int(count), 150))
    
    if not candidates:
        fallback_pool = list(BROAD_US_LIQUID_UNIVERSE)
        rng.shuffle(fallback_pool)
        return fallback_pool[:requested]
        
    requested = min(requested, len(candidates))
    return candidates[:requested]


def universe_metadata(
    cached_tickers: Iterable[str],
    *,
    count: int = 150,
    seed: int = 73021,
) -> dict:
    cached = {str(ticker).strip().upper() for ticker in cached_tickers or []}
    selected = select_unseen_tickers(cached, count=count, seed=seed)
    return {
        "tickers": selected,
        "count": len(selected),
        "seed": int(seed),
        "cached_excluded": len(cached),
        "candidate_pool": len(set(BROAD_US_LIQUID_UNIVERSE)),
        "selection_policy": "Deterministic seeded shuffle from a broad liquid-US research pool, falling back to random sampling of the universe if unused pool is exhausted.",
        "requires_market_data_validation": True,
    }
