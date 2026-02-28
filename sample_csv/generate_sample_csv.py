import csv
import json
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Tuple


@dataclass
class GenerateConfig:
    seed: int = 42
    users_per_department: int = 8
    num_tables: int = 30
    days: int = 7
    window_minutes: int = 60
    events_per_user_per_day: Tuple[int, int] = (20, 80)
    action_weights: Dict[str, float] = None
    base_dbu_range: Tuple[float, float] = (0.00, 0.40)
    night_bonus_range: Tuple[float, float] = (0.10, 0.80)

    def __post_init__(self) -> None:
        if self.action_weights is None:
            self.action_weights = {"getTable": 0.70, "commandSubmit": 0.30}


@dataclass
class DirtyConfig:
    seed: int = 20260220
    audit_null_rate: float = 0.08
    usage_null_rate: float = 0.08
    audit_duplicate_rate: float = 0.10
    usage_overlap_duplicate_rate: float = 0.10
    leading_space_rate: float = 0.05
    column_shift_rate: float = 0.01


JST = timezone(timedelta(hours=9))
OUT_DIR = Path(__file__).resolve().parent

AUDIT_CLEAN_CSV = OUT_DIR / "audit_clean.csv"
AUDIT_DIRTY_CSV = OUT_DIR / "audit_dirty.csv"
USAGE_CLEAN_CSV = OUT_DIR / "usage_clean.csv"
USAGE_DIRTY_CSV = OUT_DIR / "usage_dirty.csv"
USER_LIST_CSV = OUT_DIR / "user_list.csv"

AUDIT_COLUMNS = [
    "event_id",
    "event_time",
    "action_name",
    "user",
    "request_params",
    "resource_name",
    "source_ip",
]

USAGE_COLUMNS = [
    "record_id",
    "usage_start_time",
    "usage_end_time",
    "usage_quantity",
    "sku",
    "workspace_id",
    "identity_metadata",
]

USER_LIST_COLUMNS = ["email", "last_name", "first_name", "department_1", "department_2"]

DEPARTMENT_1_LIST = ["営業部", "システムエンジニア部", "経理部", "購買部", "人事部", "法務部", "マーケティング部"]
DEPARTMENT_2_LIST = ["第一課", "第二課", "第三課"]
WORKSPACE_ID_BY_DEPARTMENT = {
    "営業部": 101001,
    "システムエンジニア部": 101002,
    "経理部": 101003,
    "購買部": 101004,
    "人事部": 101005,
    "法務部": 101006,
    "マーケティング部": 101007,
}


def iso(ts: datetime) -> str:
    return ts.strftime("%Y-%m-%dT%H:%M:%S")


def weighted_choice(weight_map: Dict[str, float], rng: random.Random) -> str:
    r = rng.random()
    cum = 0.0
    for key, weight in weight_map.items():
        cum += weight
        if r <= cum:
            return key
    return list(weight_map.keys())[-1]


def random_ip(rng: random.Random) -> str:
    return f"10.{rng.randint(0,255)}.{rng.randint(0,255)}.{rng.randint(1,254)}"


def make_users(users_per_department: int, rng: random.Random) -> List[Dict[str, str]]:
    # Generate Japanese display names for audit/user JSON.
    last_names = [
        "佐藤", "鈴木", "高橋", "田中", "伊藤", "渡辺", "山本", "中村", "小林", "加藤",
        "吉田", "山田", "佐々木", "山口", "斎藤", "松本", "井上", "木村", "林", "清水",
    ]
    first_names = [
        "太郎", "花子", "健", "美咲", "大輔", "結衣", "翔", "優子", "直樹", "彩",
        "悠斗", "真由", "蓮", "沙織", "悠真", "愛", "颯太", "杏奈", "拓也", "美優",
    ]
    users: List[Dict[str, str]] = []
    email_seq = 0
    for department_1 in DEPARTMENT_1_LIST:
        for _ in range(users_per_department):
            # 部署が違えば同姓同名を許容するため、名前重複は許容してランダム採番する。
            first_name = rng.choice(first_names)
            last_name = rng.choice(last_names)
            users.append(
                {
                    "email": f"user{email_seq:03d}@example.com",
                    "name": f"{last_name} {first_name}",
                    "first_name": first_name,
                    "last_name": last_name,
                    "department_1": department_1,
                    "department_2": rng.choice(DEPARTMENT_2_LIST),
                }
            )
            email_seq += 1
    return users


def make_tables(n: int, rng: random.Random) -> List[str]:
    catalogs = ["main", "dev", "prod"]
    schemas = ["sales", "finance", "ops", "ml", "hr"]
    return [f"{rng.choice(catalogs)}.{rng.choice(schemas)}.table_{i:03d}" for i in range(n)]


def is_night_hour(hour: int) -> bool:
    return hour in (0, 1, 2, 3, 4, 5, 22, 23)


def build_windows(start_date_jst: datetime, days: int, window_minutes: int) -> List[Tuple[datetime, datetime]]:
    windows: List[Tuple[datetime, datetime]] = []
    current = start_date_jst
    end = start_date_jst + timedelta(days=days)
    while current < end:
        w_start = current
        w_end = current + timedelta(minutes=window_minutes)
        windows.append((w_start, w_end))
        current = w_end
    return windows


def generate_usage_rows(
    users: List[Dict[str, str]],
    windows: List[Tuple[datetime, datetime]],
    cfg: GenerateConfig,
    rng: random.Random,
) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    record_seq = 1
    for user in users:
        for w_start, w_end in windows:
            dbu = rng.uniform(*cfg.base_dbu_range)
            if is_night_hour(w_start.hour) and rng.random() < 0.35:
                dbu += rng.uniform(*cfg.night_bonus_range)
            if rng.random() < 0.15:
                dbu = 0.0

            identity_metadata = {"run_as": {"email": user["email"]}, "actor_type": "user"}
            rows.append(
                {
                    "record_id": f"rec_{record_seq:08d}",
                    "usage_start_time": iso(w_start),
                    "usage_end_time": iso(w_end),
                    "usage_quantity": round(dbu, 4),
                    "sku": "ALL_PURPOSE",
                    "workspace_id": WORKSPACE_ID_BY_DEPARTMENT[user["department_1"]],
                    "identity_metadata": json.dumps(identity_metadata, ensure_ascii=False),
                }
            )
            record_seq += 1
    return rows


def generate_audit_rows(
    users: List[Dict[str, str]],
    tables: List[str],
    windows: List[Tuple[datetime, datetime]],
    cfg: GenerateConfig,
    rng: random.Random,
    start_date_jst: datetime,
) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    event_seq = 1
    days_list = [start_date_jst.date() + timedelta(days=i) for i in range(cfg.days)]

    for user in users:
        for day in days_list:
            n_events = rng.randint(*cfg.events_per_user_per_day)
            day_windows = [(ws, we) for ws, we in windows if ws.date() == day]

            for _ in range(n_events):
                ws, we = rng.choice(day_windows)
                delta_seconds = int((we - ws).total_seconds()) - 1
                ev_time = ws + timedelta(seconds=rng.randint(0, max(delta_seconds, 0)))
                action = weighted_choice(cfg.action_weights, rng)
                table_name = rng.choice(tables)
                user_json = json.dumps({"email": user["email"], "name": user["name"]}, ensure_ascii=False)
                request_params = json.dumps({"full_name_arg": table_name}, ensure_ascii=False)

                rows.append(
                    {
                        "event_id": f"evt_{event_seq:08d}",
                        "event_time": iso(ev_time),
                        "action_name": action,
                        "user": user_json,
                        "request_params": request_params,
                        "resource_name": table_name,
                        "source_ip": random_ip(rng),
                    }
                )
                event_seq += 1
    return rows


def make_user_list_rows(users: List[Dict[str, str]]) -> List[Dict[str, str]]:
    return [
        {
            "email": user["email"],
            "last_name": user["last_name"],
            "first_name": user["first_name"],
            "department_1": user["department_1"],
            "department_2": user["department_2"],
        }
        for user in users
    ]


def calculate_count(total: int, rate: float, min_value: int = 0) -> int:
    if total <= 0 or rate <= 0:
        return 0
    return min(total, max(min_value, int(round(total * rate))))


def pick_unique_indices(total: int, count: int, rng: random.Random) -> List[int]:
    if total <= 0 or count <= 0:
        return []
    return rng.sample(range(total), min(total, count))


def extract_user_email(user_json_str: str) -> str:
    try:
        return json.loads(user_json_str).get("email", "")
    except Exception:
        return ""


def set_user_email(user_json_str: str, new_email: str, remove: bool = False) -> str:
    try:
        obj = json.loads(user_json_str)
        if remove:
            obj.pop("email", None)
        else:
            obj["email"] = new_email
        return json.dumps(obj, ensure_ascii=False)
    except Exception:
        return user_json_str


def extract_usage_email(identity_metadata_str: str) -> str:
    try:
        return json.loads(identity_metadata_str).get("run_as", {}).get("email", "")
    except Exception:
        return ""


def set_usage_email(identity_metadata_str: str, new_email: str) -> str:
    try:
        obj = json.loads(identity_metadata_str)
        if "run_as" not in obj or not isinstance(obj["run_as"], dict):
            obj["run_as"] = {}
        obj["run_as"]["email"] = new_email
        return json.dumps(obj, ensure_ascii=False)
    except Exception:
        return identity_metadata_str


def clone_records(rows: List[Dict[str, object]]) -> List[Dict[str, object]]:
    return [dict(row) for row in rows]


def apply_dirty_audit(audit_clean_rows: List[Dict[str, object]], cfg: DirtyConfig, rng: random.Random):
    rows = clone_records(audit_clean_rows)
    stats: Dict[str, int] = {}
    n = len(rows)

    null_count = calculate_count(n, cfg.audit_null_rate)
    null_indices = pick_unique_indices(n, null_count, rng)
    null_event_time = 0
    null_action_name = 0
    null_user_email = 0
    for idx in null_indices:
        target = rng.choice(["event_time", "action_name", "user_email"])
        if target == "event_time":
            rows[idx]["event_time"] = None
            null_event_time += 1
        elif target == "action_name":
            rows[idx]["action_name"] = None
            null_action_name += 1
        else:
            rows[idx]["user"] = set_user_email(str(rows[idx]["user"]), "", remove=True)
            null_user_email += 1

    leading_space_count = calculate_count(n, cfg.leading_space_rate)
    leading_space_indices = pick_unique_indices(n, leading_space_count, rng)
    leading_space_action_name = 0
    leading_space_resource_name = 0
    leading_space_user_email = 0
    for idx in leading_space_indices:
        target = rng.choice(["action_name", "resource_name", "user_email"])
        if target == "action_name":
            current = "" if rows[idx]["action_name"] is None else str(rows[idx]["action_name"])
            rows[idx]["action_name"] = f" {current}"
            leading_space_action_name += 1
        elif target == "resource_name":
            current = "" if rows[idx]["resource_name"] is None else str(rows[idx]["resource_name"])
            rows[idx]["resource_name"] = f" {current}"
            leading_space_resource_name += 1
        else:
            email = extract_user_email(str(rows[idx]["user"]))
            if email:
                rows[idx]["user"] = set_user_email(str(rows[idx]["user"]), f" {email}")
                leading_space_user_email += 1

    dup_count = calculate_count(n, cfg.audit_duplicate_rate)
    dup_rows = [dict(rows[rng.randrange(n)]) for _ in range(dup_count)] if n > 0 else []
    rows.extend(dup_rows)

    stats["rows_before_dirty"] = n
    stats["rows_after_dirty"] = len(rows)
    stats["null_event_time"] = null_event_time
    stats["null_action_name"] = null_action_name
    stats["null_user_email_missing_in_json"] = null_user_email
    stats["leading_space_action_name"] = leading_space_action_name
    stats["leading_space_resource_name"] = leading_space_resource_name
    stats["leading_space_user_email"] = leading_space_user_email
    stats["duplicate_rows_added"] = len(dup_rows)

    return rows, stats


def apply_dirty_usage(usage_clean_rows: List[Dict[str, object]], cfg: DirtyConfig, rng: random.Random):
    rows = clone_records(usage_clean_rows)
    stats: Dict[str, int] = {}
    n = len(rows)

    null_count = calculate_count(n, cfg.usage_null_rate)
    null_indices = pick_unique_indices(n, null_count, rng)
    usage_quantity_null = 0
    usage_quantity_empty = 0
    for idx in null_indices:
        if rng.random() < 0.5:
            rows[idx]["usage_quantity"] = None
            usage_quantity_null += 1
        else:
            rows[idx]["usage_quantity"] = ""
            usage_quantity_empty += 1

    leading_space_count = calculate_count(n, cfg.leading_space_rate)
    leading_space_indices = pick_unique_indices(n, leading_space_count, rng)
    leading_space_usage_email = 0
    for idx in leading_space_indices:
        email = extract_usage_email(str(rows[idx]["identity_metadata"]))
        if email:
            rows[idx]["identity_metadata"] = set_usage_email(str(rows[idx]["identity_metadata"]), f" {email}")
            leading_space_usage_email += 1

    overlap_count = calculate_count(n, cfg.usage_overlap_duplicate_rate)
    overlap_rows: List[Dict[str, object]] = []
    for idx in pick_unique_indices(n, overlap_count, rng):
        row = dict(rows[idx])
        start_dt = datetime.fromisoformat(str(row["usage_start_time"]))
        end_dt = datetime.fromisoformat(str(row["usage_end_time"]))
        row["usage_start_time"] = iso(start_dt + timedelta(minutes=15))
        row["usage_end_time"] = iso(end_dt + timedelta(minutes=15))
        overlap_rows.append(row)

    rows.extend(overlap_rows)

    stats["rows_before_dirty"] = n
    stats["rows_after_dirty"] = len(rows)
    stats["usage_quantity_null"] = usage_quantity_null
    stats["usage_quantity_empty"] = usage_quantity_empty
    stats["leading_space_user_email"] = leading_space_usage_email
    stats["overlap_rows_added"] = len(overlap_rows)

    return rows, stats


def normalize_csv_value(value) -> str:
    if value is None:
        return ""
    return str(value)


def write_clean_csv(rows: List[Dict[str, object]], columns: List[str], out_path: Path) -> None:
    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({col: normalize_csv_value(row.get(col)) for col in columns})


def write_dirty_csv_with_column_shift(
    rows: List[Dict[str, object]],
    columns: List[str],
    out_path: Path,
    cfg: DirtyConfig,
    rng: random.Random,
) -> Dict[str, int]:
    total = len(rows)
    shift_total = calculate_count(total, cfg.column_shift_rate)
    if total >= 2 and shift_total == 1:
        shift_total = 2

    shift_indices = pick_unique_indices(total, shift_total, rng)
    missing_count = shift_total // 2
    missing_indices = set(shift_indices[:missing_count])
    extra_indices = set(shift_indices[missing_count:])

    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(columns)

        for idx, record in enumerate(rows):
            row_values = [normalize_csv_value(record.get(col)) for col in columns]
            if idx in missing_indices:
                writer.writerow(row_values[:-1])
            elif idx in extra_indices:
                writer.writerow(row_values + ["unexpected_value"])
            else:
                writer.writerow(row_values)

    return {
        "column_shift_rows_total": shift_total,
        "column_shift_missing_col_rows": len(missing_indices),
        "column_shift_extra_col_rows": len(extra_indices),
    }


def main() -> None:
    gen_cfg = GenerateConfig()
    dirty_cfg = DirtyConfig()

    clean_rng = random.Random(gen_cfg.seed)
    dirty_rng_audit = random.Random(dirty_cfg.seed)
    dirty_rng_usage = random.Random(dirty_cfg.seed + 1)
    dirty_rng_audit_shift = random.Random(dirty_cfg.seed + 2)
    dirty_rng_usage_shift = random.Random(dirty_cfg.seed + 3)

    start_date_jst = datetime.now(JST).replace(minute=0, second=0, microsecond=0) - timedelta(days=gen_cfg.days)

    users = make_users(gen_cfg.users_per_department, clean_rng)
    tables = make_tables(gen_cfg.num_tables, clean_rng)
    windows = build_windows(start_date_jst, gen_cfg.days, gen_cfg.window_minutes)

    usage_clean_rows = generate_usage_rows(users, windows, gen_cfg, clean_rng)
    audit_clean_rows = generate_audit_rows(users, tables, windows, gen_cfg, clean_rng, start_date_jst)
    user_list_rows = make_user_list_rows(users)

    write_clean_csv(audit_clean_rows, AUDIT_COLUMNS, AUDIT_CLEAN_CSV)
    write_clean_csv(usage_clean_rows, USAGE_COLUMNS, USAGE_CLEAN_CSV)
    write_clean_csv(user_list_rows, USER_LIST_COLUMNS, USER_LIST_CSV)

    audit_dirty_rows, audit_stats = apply_dirty_audit(audit_clean_rows, dirty_cfg, dirty_rng_audit)
    usage_dirty_rows, usage_stats = apply_dirty_usage(usage_clean_rows, dirty_cfg, dirty_rng_usage)

    audit_shift_stats = write_dirty_csv_with_column_shift(
        audit_dirty_rows,
        AUDIT_COLUMNS,
        AUDIT_DIRTY_CSV,
        dirty_cfg,
        dirty_rng_audit_shift,
    )
    usage_shift_stats = write_dirty_csv_with_column_shift(
        usage_dirty_rows,
        USAGE_COLUMNS,
        USAGE_DIRTY_CSV,
        dirty_cfg,
        dirty_rng_usage_shift,
    )

    print("Saved files:")
    print(f"  {AUDIT_CLEAN_CSV}")
    print(f"  {AUDIT_DIRTY_CSV}")
    print(f"  {USAGE_CLEAN_CSV}")
    print(f"  {USAGE_DIRTY_CSV}")
    print(f"  {USER_LIST_CSV}")

    print("\nRow counts:")
    print(f"  audit_clean rows: {len(audit_clean_rows)}")
    print(f"  audit_dirty rows: {len(audit_dirty_rows)}")
    print(f"  usage_clean rows: {len(usage_clean_rows)}")
    print(f"  usage_dirty rows: {len(usage_dirty_rows)}")
    print(f"  user_list rows : {len(user_list_rows)}")

    print("\nDirty summary (audit):")
    for key, value in {**audit_stats, **audit_shift_stats}.items():
        print(f"  {key}: {value}")

    print("\nDirty summary (usage):")
    for key, value in {**usage_stats, **usage_shift_stats}.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
