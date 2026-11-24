
import json
import io
import pandas as pd
import requests

BASE_URL = "https://davidmegginson.github.io/ourairports-data"

def load_csv(name: str) -> pd.DataFrame:
    url = f"{BASE_URL}/{name}.csv"
    print(f"[+] Загрузка {url} ...")
    resp = requests.get(url, timeout=120)
    resp.raise_for_status()
    return pd.read_csv(io.StringIO(resp.text), encoding="utf-8")


def load_all():
    airports  = load_csv("airports")
    runways   = load_csv("runways")
    countries = load_csv("countries")
    return airports, runways, countries


def clean_airports(df: pd.DataFrame) -> pd.DataFrame:
    str_cols = df.select_dtypes(include="object").columns
    for c in str_cols:
        df[c] = df[c].astype(str).str.strip()
        df[c] = df[c].replace({"nan": None, "": None})

    df["latitude_deg"]  = pd.to_numeric(df["latitude_deg"],  errors="coerce")
    df["longitude_deg"] = pd.to_numeric(df["longitude_deg"], errors="coerce")
    df["elevation_ft"]  = pd.to_numeric(df["elevation_ft"],  errors="coerce")

    df["scheduled_service"] = df["scheduled_service"].map(
        {"yes": True, "no": False}
    )

    df = df.drop_duplicates(subset="id").reset_index(drop=True)
    return df


def clean_runways(df: pd.DataFrame) -> pd.DataFrame:
    str_cols = df.select_dtypes(include="object").columns
    for c in str_cols:
        df[c] = df[c].astype(str).str.strip()

    df["length_ft"] = pd.to_numeric(df["length_ft"], errors="coerce")
    df["width_ft"]  = pd.to_numeric(df["width_ft"],  errors="coerce")

    for col in ("lighted", "closed"):
        df[col] = df[col].astype(str).str.strip().map(
            {"1": True, "0": False, "True": True, "False": False}
        ).fillna(False)

    df = df[~df["closed"]]
    df = df[(df["length_ft"] > 0) & (df["length_ft"] < 20000)]

    return df.reset_index(drop=True)



def build_dataset(airports, runways, countries):
    rw_agg = (
        runways.groupby("airport_ref")
        .agg(
            number_of_runways=("id", "count"),
            avg_runway_length_ft=("length_ft", "mean"),
            max_runway_length_ft=("length_ft", "max"),
        )
        .reset_index()
        .rename(columns={"airport_ref": "airport_id"})
    )

    df = airports.merge(rw_agg, how="left", left_on="id", right_on="airport_id")
    df["number_of_runways"]     = df["number_of_runways"].fillna(0).astype(int)
    df["avg_runway_length_ft"]  = df["avg_runway_length_ft"].round(1)
    df["max_runway_length_ft"]  = df["max_runway_length_ft"]

    df = df.merge(
        countries[["code", "name"]].rename(
            columns={"code": "iso_country", "name": "country_name"}
        ),
        how="left", on="iso_country"
    )
    df = df[df["number_of_runways"] > 0].reset_index(drop=True)
    return df

# 3
def export_json(df: pd.DataFrame, runways: pd.DataFrame,
                path: str = "airports.json", limit: int = None):
    if limit:
        df_exp = df.head(limit).copy()
    else:
        df_exp = df.copy()

    rw_by_airport = (
        runways.groupby("airport_ref")
        .apply(lambda g: [
            {
                "length_ft": (None if pd.isna(r.length_ft) else int(r.length_ft)),
                "width_ft":(None if pd.isna(r.width_ft)  else int(r.width_ft)),
                "surface": r.surface if isinstance(r.surface, str) else None,
                "lighted": bool(r.lighted),
            }
            for r in g.itertuples()
        ])
        .to_dict()
    )

    records = []
    for row in df_exp.itertuples():
        rw_list = rw_by_airport.get(row.id, [])
        records.append({
            "airport_id":          int(row.id),
            "name":                row.name,
            "city":                row.municipality if isinstance(row.municipality, str) else None,
            "country":             row.country_name,
            "country_code":        row.iso_country,
            "region":              row.iso_region,
            "type":                row.type,
            "latitude":            None if pd.isna(row.latitude_deg)  else float(row.latitude_deg),
            "longitude":           None if pd.isna(row.longitude_deg) else float(row.longitude_deg),
            "elevation_ft":        None if pd.isna(row.elevation_ft)  else int(row.elevation_ft),
            "number_of_runways":   int(row.number_of_runways),
            "avg_runway_length_ft": None if pd.isna(row.avg_runway_length_ft)
                                     else float(row.avg_runway_length_ft),
            "max_runway_length_ft": None if pd.isna(row.max_runway_length_ft)
                                     else float(row.max_runway_length_ft),
            "scheduled_service":   bool(row.scheduled_service) if pd.notna(row.scheduled_service) else None,
            "iata_code":           row.iata_code if isinstance(row.iata_code, str) else None,
            "icao_code":           row.ident,
            "runways":             rw_list,
        })

    with open(path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    print(f"[+] JSON сохранён: {path}  (записей: {len(records)})")


def run_queries(df: pd.DataFrame):
    print("\n" + "="*70)
    print("Общее число аэропортов")
    print("="*70)
    print(f"Всего аэропортов: {len(df)}")

    print("\n" + "="*70)
    print("Все аэропорты России")
    print("="*70)
    ru = df[df["iso_country"] == "RU"][
        ["name", "municipality", "number_of_runways", "type"]
    ].sort_values("number_of_runways", ascending=False)
    print(f"Найдено: {len(ru)} аэропортов (показаны первые 10)")
    print(ru.head(10).to_string(index=False))

    print("\n" + "="*70)
    print("Самые широкие аэропорты")
    print("="*70)
    top = df.nlargest(10, "number_of_runways")[
        ["name", "municipality", "country_name", "number_of_runways"]
    ]
    print(top.to_string(index=False))

    print("\n" + "="*70)
    print("Среднее число полос по типу аэропорта в Европе")
    print("="*70)
    europe_codes = [
        "RU","DE","FR","GB","IT","ES","PL","UA","NL","BE","SE","NO",
        "FI","DK","CH","AT","CZ","GR","PT","IE","RO","HU","BG","SK",
    ]
    eu = df[df["iso_country"].isin(europe_codes)]
    q4 = (
        eu.groupby("type")
          .agg(avg_runways=("number_of_runways", "mean"),
               airport_count=("id", "count"))
          .round(2)
          .sort_values("avg_runways", ascending=False)
    )
    print(q4.to_string())

    print("\n" + "="*70)
    print("Страны с > 10 аэропортами регулярного сообщения и средней длиной ВПП > 8000 фт")
    print("="*70)
    sub = df[df["scheduled_service"] == True].copy()
    q5 = (
        sub.groupby("country_name")
           .agg(num_airports=("id", "count"),
                avg_runway_length=("avg_runway_length_ft", "mean"))
           .query("num_airports > 10 and avg_runway_length > 8000")
           .round(1)
           .sort_values("num_airports", ascending=False)
    )
    print(q5.to_string())

def main():
    airports_raw, runways_raw, countries = load_all()

    airports = clean_airports(airports_raw)
    runways  = clean_runways(runways_raw)

    df = build_dataset(airports, runways, countries)
    print(f"[+] Итоговый датафрейм: {df.shape[0]} строк, {df.shape[1]} столбцов")

    # экспорт 500 аэропортов
    top500 = df.sort_values("number_of_runways", ascending=False).head(500)
    export_json(top500, runways, path="airports.json")

    # Аналитика по полному набору
    run_queries(df)


if __name__ == "__main__":
    main()