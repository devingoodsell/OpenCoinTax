#!/usr/bin/env python3
"""Convert raw Koinly API JSON exports to properly formatted CSVs.

Usage:
    python json_to_csv.py --transactions raw_transactions.json --wallets raw_wallets.json

    Or specify an input directory containing both files:
    python json_to_csv.py --input-dir ~/Downloads

Output (written to ./output/):
    wallets.csv           - All wallets with IDs, names, types
    transactions.csv      - All transactions with From/To wallet names
    transactions_2025.csv - Filtered to 2025 tax year only
    summary.json          - Quick stats overview
"""

import argparse
import csv
import json
import os
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path


def load_json(filepath):
    with open(filepath, "r") as f:
        return json.load(f)


def format_date(iso_str):
    """Convert ISO 8601 date string to human-readable format."""
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    except (ValueError, TypeError):
        return iso_str


def build_wallet_lookup(wallets):
    """Build a dict mapping wallet ID -> wallet name."""
    lookup = {}
    for w in wallets:
        wid = str(w.get("id", ""))
        name = w.get("name", "")
        if wid and name:
            lookup[wid] = name
    return lookup


def extract_wallet_name(side, wallet_lookup):
    """Extract wallet name from a transaction side (from/to), using the
    lookup table as a fallback if the nested wallet object is missing."""
    if not side:
        return "", ""

    wallet = side.get("wallet") or {}
    name = wallet.get("name", "")
    wid = str(wallet.get("id", ""))

    # Fallback: use wallet_id field if wallet object is incomplete
    if not name and wid and wid in wallet_lookup:
        name = wallet_lookup[wid]

    # Fallback: check for wallet_id at the side level
    if not name:
        side_wid = str(side.get("wallet_id", ""))
        if side_wid and side_wid in wallet_lookup:
            name = wallet_lookup[side_wid]
            wid = side_wid

    return name, wid


def process_transactions(transactions, wallet_lookup):
    """Convert raw API transaction objects into flat dicts for CSV output."""
    rows = []
    for tx in transactions:
        from_side = tx.get("from") or {}
        to_side = tx.get("to") or {}
        fee_side = tx.get("fee") or {}

        from_wallet_name, from_wallet_id = extract_wallet_name(from_side, wallet_lookup)
        to_wallet_name, to_wallet_id = extract_wallet_name(to_side, wallet_lookup)

        rows.append({
            "Date": format_date(tx.get("date")),
            "Type": tx.get("type", ""),
            "Label": tx.get("label", ""),
            "Description": tx.get("description", ""),
            "From Wallet": from_wallet_name,
            "From Wallet ID": from_wallet_id,
            "Sent Amount": from_side.get("amount", ""),
            "Sent Currency": (from_side.get("currency") or {}).get("symbol", ""),
            "To Wallet": to_wallet_name,
            "To Wallet ID": to_wallet_id,
            "Received Amount": to_side.get("amount", ""),
            "Received Currency": (to_side.get("currency") or {}).get("symbol", ""),
            "Fee Amount": fee_side.get("amount", ""),
            "Fee Currency": (fee_side.get("currency") or {}).get("symbol", ""),
            "Net Worth (USD)": tx.get("net_value", ""),
            "TxHash": tx.get("txhash", ""),
            "Koinly ID": tx.get("id", ""),
            "Gain/Loss": tx.get("gain", ""),
        })
    return rows


def write_csv(filepath, rows, fieldnames):
    with open(filepath, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"  Wrote {len(rows)} rows -> {filepath}")


def generate_summary(rows, wallets):
    """Generate a summary dict with stats about the data."""
    types = Counter(r["Type"] for r in rows)
    currencies_sent = Counter(r["Sent Currency"] for r in rows if r["Sent Currency"])
    currencies_recv = Counter(r["Received Currency"] for r in rows if r["Received Currency"])
    from_wallets = Counter(r["From Wallet"] for r in rows if r["From Wallet"])
    to_wallets = Counter(r["To Wallet"] for r in rows if r["To Wallet"])

    dates = [r["Date"] for r in rows if r["Date"]]
    date_range = {"earliest": min(dates) if dates else "", "latest": max(dates) if dates else ""}

    # Year breakdown
    years = Counter()
    for d in dates:
        try:
            years[d[:4]] += 1
        except (IndexError, TypeError):
            pass

    return {
        "total_transactions": len(rows),
        "total_wallets": len(wallets),
        "wallet_names": [w.get("name", "") for w in wallets],
        "date_range": date_range,
        "transactions_by_type": dict(types.most_common()),
        "transactions_by_year": dict(sorted(years.items())),
        "currencies_sent": dict(currencies_sent.most_common(20)),
        "currencies_received": dict(currencies_recv.most_common(20)),
        "from_wallet_activity": dict(from_wallets.most_common()),
        "to_wallet_activity": dict(to_wallets.most_common()),
        "transactions_with_from_wallet": sum(1 for r in rows if r["From Wallet"]),
        "transactions_with_to_wallet": sum(1 for r in rows if r["To Wallet"]),
        "transactions_missing_both_wallets": sum(
            1 for r in rows if not r["From Wallet"] and not r["To Wallet"]
        ),
    }


def main():
    parser = argparse.ArgumentParser(description="Convert Koinly raw JSON to CSV")
    parser.add_argument("--transactions", "-t", help="Path to raw_transactions.json")
    parser.add_argument("--wallets", "-w", help="Path to raw_wallets.json")
    parser.add_argument(
        "--input-dir", "-i",
        help="Directory containing raw_transactions.json and raw_wallets.json"
    )
    parser.add_argument(
        "--output-dir", "-o",
        default=str(Path(__file__).resolve().parent / "output"),
        help="Output directory (default: ./output/)"
    )
    parser.add_argument(
        "--tax-year", "-y",
        default="2025",
        help="Tax year to filter for (default: 2025)"
    )
    args = parser.parse_args()

    # Resolve input files
    if args.input_dir:
        input_dir = Path(args.input_dir)
        txn_file = input_dir / "raw_transactions.json"
        wal_file = input_dir / "raw_wallets.json"
    else:
        txn_file = Path(args.transactions) if args.transactions else None
        wal_file = Path(args.wallets) if args.wallets else None

    if not txn_file or not txn_file.exists():
        # Try common download locations
        for candidate in [
            Path.home() / "Downloads" / "raw_transactions.json",
            Path(__file__).resolve().parent / "raw_transactions.json",
            Path(__file__).resolve().parent / "output" / "raw_transactions.json",
        ]:
            if candidate.exists():
                txn_file = candidate
                break

    if not wal_file or not wal_file.exists():
        for candidate in [
            Path.home() / "Downloads" / "raw_wallets.json",
            Path(__file__).resolve().parent / "raw_wallets.json",
            Path(__file__).resolve().parent / "output" / "raw_wallets.json",
        ]:
            if candidate.exists():
                wal_file = candidate
                break

    if not txn_file or not txn_file.exists():
        print("ERROR: Cannot find raw_transactions.json")
        print("Specify with: --transactions PATH or --input-dir DIR")
        sys.exit(1)

    print(f"Loading transactions from: {txn_file}")
    transactions = load_json(txn_file)
    print(f"  Loaded {len(transactions)} transactions")

    wallets = []
    wallet_lookup = {}
    if wal_file and wal_file.exists():
        print(f"Loading wallets from: {wal_file}")
        wallets = load_json(wal_file)
        wallet_lookup = build_wallet_lookup(wallets)
        print(f"  Loaded {len(wallets)} wallets")
    else:
        print("WARNING: No wallets file found. Wallet names will come from transaction data only.")

    # Process
    print("\nProcessing transactions...")
    rows = process_transactions(transactions, wallet_lookup)

    # Output
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    txn_fields = [
        "Date", "Type", "Label", "Description",
        "From Wallet", "From Wallet ID",
        "Sent Amount", "Sent Currency",
        "To Wallet", "To Wallet ID",
        "Received Amount", "Received Currency",
        "Fee Amount", "Fee Currency",
        "Net Worth (USD)", "TxHash", "Koinly ID", "Gain/Loss",
    ]

    # All transactions
    write_csv(output_dir / "transactions.csv", rows, txn_fields)

    # Tax year filter
    tax_year = args.tax_year
    year_rows = [r for r in rows if r["Date"].startswith(tax_year)]
    write_csv(output_dir / f"transactions_{tax_year}.csv", year_rows, txn_fields)

    # Wallets CSV
    if wallets:
        wal_fields = ["Koinly ID", "Name", "Type", "Blockchain", "Address"]
        wal_rows = [
            {
                "Koinly ID": w.get("id", ""),
                "Name": w.get("name", ""),
                "Type": w.get("wallet_type", ""),
                "Blockchain": w.get("blockchain", ""),
                "Address": w.get("address", ""),
            }
            for w in wallets
        ]
        write_csv(output_dir / "wallets.csv", wal_rows, wal_fields)

    # Summary
    summary = generate_summary(rows, wallets)
    summary_path = output_dir / "summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"  Wrote summary -> {summary_path}")

    # Print summary to console
    print(f"\n{'='*60}")
    print(f"Summary")
    print(f"{'='*60}")
    print(f"  Total transactions:  {summary['total_transactions']}")
    print(f"  Total wallets:       {summary['total_wallets']}")
    print(f"  Date range:          {summary['date_range']['earliest'][:10]} to {summary['date_range']['latest'][:10]}")
    print(f"  {tax_year} transactions: {len(year_rows)}")
    print(f"  With From Wallet:    {summary['transactions_with_from_wallet']}")
    print(f"  With To Wallet:      {summary['transactions_with_to_wallet']}")
    print(f"  Missing both:        {summary['transactions_missing_both_wallets']}")
    print(f"\n  Wallet activity (To):")
    for name, count in sorted(summary["to_wallet_activity"].items(), key=lambda x: -x[1]):
        print(f"    {name}: {count} transactions")
    print(f"\n  Transaction types:")
    for ttype, count in sorted(summary["transactions_by_type"].items(), key=lambda x: -x[1]):
        print(f"    {ttype}: {count}")


if __name__ == "__main__":
    main()
