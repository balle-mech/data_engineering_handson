# --------------------------------------------
# Generate sample Audit CSV + Usage CSV
# (hourly windows x 7 days, with matching events)
# --------------------------------------------
import os
import json
import random
from datetime import datetime, timedelta, timezone
import pandas as pd

# ========== Parameters ==========
SEED = 42
NUM_USERS = 20
NUM_TABLES = 30

DAYS = 7                 # 7 days
WINDOW_MINUTES = 60      # 1 hour window
EVENTS_PER_USER_PER_DAY = (20, 80)  # min/max events per user per day (random)
ACTION_WEIGHTS = {
    "getTable": 0.70,
    "commandSubmit": 0.30
}

# DBU distribution per hour window (roughly "realistic")
# You can tweak to make night batch heavier etc.
BASE_DBU_RANGE = (0.00, 0.40)  # typical per user per hour
NIGHT_BONUS_RANGE = (0.10, 0.80)  # extra at night for some hours

# Timezone: Asia/Tokyo (UTC+9)
JST = timezone(timedelta(hours=9))
START_DATE_JST = datetime.now(JST).replace(minute=0, second=0, microsecond=0) - timedelta(days=DAYS)

# Output
OUT_DIR = "./"  # change if you like
AUDIT_CSV = os.path.join(OUT_DIR, "audit.csv")
USAGE_CSV = os.path.join(OUT_DIR, "usage.csv")
USER_LIST_CSV = os.path.join(OUT_DIR, "user_list.csv")

# ========== Helpers ==========
random.seed(SEED)


def iso(ts: datetime) -> str:
    # ISO8601 without timezone suffix for simplicity (works with to_timestamp in Spark)
    # If you prefer "2026-02-02T10:00:00+09:00", change below.
    return ts.strftime("%Y-%m-%dT%H:%M:%S")


def weighted_choice(weight_map: dict) -> str:
    r = random.random()
    cum = 0.0
    for k, w in weight_map.items():
        cum += w
        if r <= cum:
            return k
    return list(weight_map.keys())[-1]


def random_ip() -> str:
    # Private-ish range; feel free to change to more realistic public IPs
    return f"10.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}"


def make_users(n: int):
    # Generate Japanese display names for audit/user JSON
    last_names = [
        "佐藤", "鈴木", "高橋", "田中", "伊藤", "渡辺", "山本", "中村", "小林", "加藤",
        "吉田", "山田", "佐々木", "山口", "斎藤", "松本", "井上", "木村", "林", "清水"
    ]
    first_names = [
        "太郎", "花子", "健", "美咲", "大輔", "結衣", "翔", "優子", "直樹", "彩",
        "悠斗", "真由", "蓮", "沙織", "悠真", "愛", "颯太", "杏奈", "拓也", "美優"
    ]

    users = []
    # 名前のプールを作成し、最初のnを選択する
    name_pool = [f"{ln} {fn}" for ln in last_names for fn in first_names]
    random.shuffle(name_pool)
    for i in range(n):
        name = name_pool[i % len(name_pool)]
        email = f"user{i:02d}@example.com"
        users.append({"email": email, "name": name})
    return users


def make_tables(n: int):
    # Use fully qualified names: catalog.schema.table
    catalogs = ["main", "dev", "prod"]
    schemas = ["sales", "finance", "ops", "ml", "hr"]
    tables = []
    for i in range(n):
        c = random.choice(catalogs)
        s = random.choice(schemas)
        t = f"table_{i:03d}"
        tables.append(f"{c}.{s}.{t}")
    return tables


def is_night_hour(hour: int) -> bool:
    # Example: night = 0-5 and 22-23
    return hour in (0,1,2,3,4,5,22,23)


# ========== Generate Windows (1h x 7d) ==========
users = make_users(NUM_USERS)
tables = make_tables(NUM_TABLES)

# ========== Generate User List (Bronze) ==========
department_1_list = ["営業部", "システムエンジニア部", "経理部", "購買部", "人事部", "法務部", "マーケティング部"]
department_2_list = ["第一課", "第二課", "第三課"]

user_list_rows = []
for user in users:
    name = user["name"]
    if " " in name:
        last_name, first_name = name.split(" ", 1)
    else:
        last_name, first_name = name, ""

    user_list_rows.append({
        "email": user["email"],
        "last_name": last_name,
        "first_name": first_name,
        "department_1": random.choice(department_1_list),
        "department_2": random.choice(department_2_list)
    })

user_list_df = pd.DataFrame(user_list_rows)

windows = []
current = START_DATE_JST
end = START_DATE_JST + timedelta(days=DAYS)

while current < end:
    w_start = current
    w_end = current + timedelta(minutes=WINDOW_MINUTES)
    windows.append((w_start, w_end))
    current = w_end

# ========== Generate Usage Rows ==========
usage_rows = []
for user in users:
    for (w_start, w_end) in windows:
        # Base DBU
        dbu = random.uniform(*BASE_DBU_RANGE)

        # Optional: some night windows get heavier usage
        if is_night_hour(w_start.hour) and random.random() < 0.35:
            dbu += random.uniform(*NIGHT_BONUS_RANGE)

        # Often there is zero usage for some windows
        if random.random() < 0.15:
            dbu = 0.0

        identity_metadata = {
            "run_as": {"email": user["email"]},
            "actor_type": "user"
        }

        usage_rows.append({
            "usage_start_time": iso(w_start),
            "usage_end_time": iso(w_end),
            "usage_quantity": round(dbu, 4),
            "sku": "ALL_PURPOSE",          # optional
            "workspace_id": 123456789,     # optional
            "identity_metadata": json.dumps(identity_metadata, ensure_ascii=False)
        })

usage_df = pd.DataFrame(usage_rows)

# Build a quick lookup: for each user+window, what is the window range?
# We'll use it to ensure audit.event_time always falls inside.
# Key: (email, usage_start_time_str, usage_end_time_str)
usage_index = {}
for row in usage_rows:
    key = (json.loads(row["identity_metadata"])["run_as"]["email"],
           row["usage_start_time"],
           row["usage_end_time"])
    usage_index[key] = (row["usage_start_time"], row["usage_end_time"])

# ========== Generate Audit Events aligned to Usage windows ==========
audit_rows = []

# We'll generate events per user per day, then randomly assign them into that day's hourly windows for that user.
days_list = [START_DATE_JST.date() + timedelta(days=i) for i in range(DAYS)]

for user in users:
    for d in days_list:
        n_events = random.randint(*EVENTS_PER_USER_PER_DAY)

        # Get all windows that belong to this day
        day_windows = [(ws, we) for (ws, we) in windows if ws.date() == d]

        for _ in range(n_events):
            # Pick a window for the event
            ws, we = random.choice(day_windows)

            # Choose a timestamp inside [ws, we)
            # minus 1 second to avoid edge
            delta_seconds = int((we - ws).total_seconds()) - 1
            ev_time = ws + timedelta(seconds=random.randint(0, max(delta_seconds, 0)))

            action = weighted_choice(ACTION_WEIGHTS)

            # Pick a table to access (fully qualified)
            tbl = random.choice(tables)

            # Build JSON fields
            user_json = json.dumps({"email": user["email"], "name": user["name"]}, ensure_ascii=False)
            request_params_json = json.dumps({"full_name_arg": tbl}, ensure_ascii=False)

            # Optional descriptive fields
            event_type = "access"
            event_name = "table_access"
            resource_name = tbl  # keep same as table_name for simplicity
            source_ip = random_ip()

            audit_rows.append({
                "event_time": iso(ev_time),
                "event_type": event_type,
                "event_name": event_name,
                "action_name": action,
                "user": user_json,                  # JSON string in one column
                "request_params": request_params_json,  # JSON string
                "resource_name": resource_name,
                "source_ip": source_ip
            })

audit_df = pd.DataFrame(audit_rows)

# ========== Save CSV ==========
os.makedirs(OUT_DIR, exist_ok=True)

# Ensure JSON strings are properly quoted in CSV
audit_df.to_csv(AUDIT_CSV, index=False)
usage_df.to_csv(USAGE_CSV, index=False)
user_list_df.to_csv(USER_LIST_CSV, index=False)

print("Saved:")
print(" audit:", AUDIT_CSV)
print(" usage:", USAGE_CSV)
print(" user_list:", USER_LIST_CSV)
print("Rows:")
print(" audit rows =", len(audit_df))
print(" usage rows =", len(usage_df))

# ========== (Optional) quick sanity checks ==========
# 1) Check audit times fall inside some usage window for that email
# Build a usage window list per email for faster check
from collections import defaultdict
usage_windows_by_email = defaultdict(list)
for r in usage_rows:
    email = json.loads(r["identity_metadata"])["run_as"]["email"]
    ws = datetime.fromisoformat(r["usage_start_time"]).replace(tzinfo=None)
    we = datetime.fromisoformat(r["usage_end_time"]).replace(tzinfo=None)
    usage_windows_by_email[email].append((ws, we))

def audit_has_matching_window(a_row) -> bool:
    email = json.loads(a_row["user"])["email"]
    t = datetime.fromisoformat(a_row["event_time"]).replace(tzinfo=None)
    for (ws, we) in usage_windows_by_email[email]:
        if ws <= t < we:
            return True
    return False

sample_check = audit_df.sample(min(200, len(audit_df)), random_state=SEED).to_dict("records")
ok = sum(1 for r in sample_check if audit_has_matching_window(r))
print(f"Sanity check (sample): {ok}/{len(sample_check)} audit events matched a usage window")
