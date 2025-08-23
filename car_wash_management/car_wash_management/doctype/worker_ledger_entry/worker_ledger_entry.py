import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime, cint


ENTRY_SIGN = {
    "Earning":  +1,
    "Advance":  -1,
    "Payout":   -1,
    "Correction":  1,
}


class WorkerLedgerEntry(Document):
    def validate(self):
        self.posting_datetime = self.posting_datetime or now_datetime()
        self.amount = cint(self.amount or 0)
        if self.amount <= 0:
            frappe.throw("Сумма должна быть больше 0")

        if self.entry_type == "Earning":
            if not self.appointment:
                frappe.throw("Для начисления обязателен 'Appointment'")
        else:
            # не позволяем привязывать appointment для не-начислений
            self.appointment = None

        # заполним компанию/мойку по воркеру / appointment если не передано
        if not self.company or not self.car_wash:
            self._populate_company_and_wash()

        # защитимся от дубля начисления по одному appointment+worker
        if self.entry_type == "Earning" and self.appointment:
            self._ensure_unique_earning()

    def _populate_company_and_wash(self):
        if self.appointment:
            apmt = frappe.db.get_value(
                "Car wash appointment",
                self.appointment,
                ["company", "car_wash"],
                as_dict=True,
            )
            if apmt:
                self.company = self.company or apmt.get("company")
                self.car_wash = self.car_wash or apmt.get("car_wash")
        if not self.company or not self.car_wash:
            worker = frappe.db.get_value(
                "Car wash worker",
                self.worker,
                ["company", "car_wash"],
                as_dict=True,
            )
            if worker:
                self.company = self.company or worker.get("company")
                self.car_wash = self.car_wash or worker.get("car_wash")

    def _ensure_unique_earning(self):
        exists = frappe.db.get_value(
            "Worker Ledger Entry",
            {
                "worker": self.worker,
                "entry_type": "Earning",
                "appointment": self.appointment,
                "name": ["!=", self.name],
                "docstatus": ["<", 2],
            },
            "name",
        )
        if exists:
            frappe.throw(f"Начисление для этого Appointment уже существует: {exists}")


@frappe.whitelist()
def get_worker_balance(worker: str) -> dict:
    rows = frappe.db.get_all(
        "Worker Ledger Entry",
        filters={"worker": worker, "docstatus": 1},
        fields=["entry_type", "amount"],
    )
    total = 0
    earnings = 0
    advances = 0
    payouts = 0
    for r in rows:
        sign = ENTRY_SIGN.get(r.entry_type, 1)
        amt = int(r.amount or 0)
        total += sign * amt
        if r.entry_type == "Earning":
            earnings += amt
        elif r.entry_type == "Advance":
            advances += amt
        elif r.entry_type == "Payout":
            payouts += amt
    return {
        "balance": total,
        "earnings": earnings,
        "advances": advances,
        "payouts": payouts,
    }


@frappe.whitelist()
def get_all_worker_balances(company: str | None = None,
                            car_wash: str | None = None,
                            role: str | None = None,
                            include_disabled: int | None = 0):
    """
    Возвращает список балансов по всем работникам одной выборкой.

    Параметры (опционально): company, car_wash, role (Washer/Cashier), include_disabled (0/1).
    """
    where_params = []

    worker_where = ["w.is_deleted = 0"]
    if not cint(include_disabled):
        worker_where.append("w.is_disabled = 0")
    if company:
        worker_where.append("w.company = %s")
        where_params.append(company)
    if car_wash:
        worker_where.append("w.car_wash = %s")
        where_params.append(car_wash)
    if role:
        worker_where.append("w.role = %s")
        where_params.append(role)

    # Условия для LEFT JOIN только по ключу и статусу, без доп. фильтров
    join_conds = ["e.worker = w.name", "e.docstatus = 1"]

    sql = f"""
        SELECT
            w.name AS worker,
            w.full_name AS worker_name,
            w.company AS company,
            w.car_wash AS car_wash,
            COALESCE(SUM(CASE WHEN e.entry_type = 'Earning' THEN e.amount ELSE 0 END), 0) AS earnings,
            COALESCE(SUM(CASE WHEN e.entry_type = 'Advance' THEN e.amount ELSE 0 END), 0) AS advances,
            COALESCE(SUM(CASE WHEN e.entry_type = 'Payout' THEN e.amount ELSE 0 END), 0) AS payouts,
            COALESCE(SUM(CASE
                WHEN e.entry_type = 'Earning' THEN e.amount
                WHEN e.entry_type IN ('Advance','Payout') THEN -e.amount
                ELSE 0 END), 0) AS balance
        FROM `tabCar wash worker` w
        LEFT JOIN `tabWorker Ledger Entry` e
            ON {" AND ".join(join_conds)}
        WHERE {" AND ".join(worker_where)}
        GROUP BY w.name, w.full_name, w.company, w.car_wash
        ORDER BY balance DESC
    """

    rows = frappe.db.sql(sql, where_params, as_dict=True)
    return rows


@frappe.whitelist()
def get_worker_ledger(worker: str, limit: int | None = 50):
    """
    Возвращает последние записи леджера по работнику.
    """
    limit = int(limit or 50)
    rows = frappe.get_all(
        "Worker Ledger Entry",
        filters={"worker": worker},
        fields=[
            "name",
            "posting_datetime",
            "entry_type",
            "amount",
            "company",
            "car_wash",
            "appointment",
            "note",
            "docstatus",
        ],
        order_by="posting_datetime desc, creation desc",
        limit=limit,
    )
    return rows


@frappe.whitelist()
def export_ledger_to_xls(from_date: str, to_date: str, car_wash: str | None = None,
                         worker: str | None = None, entry_type: str | None = None):
    """
    Выгрузка записей Worker Ledger Entry в XLS (SpreadsheetML) за период.
    Лист 1: Ledger — все записи по фильтрам.
    Лист 2: Начисления по дням — суммарные Earning по работникам и дням.
    """
    from io import BytesIO
    from frappe.utils import getdate, add_days

    # validate dates
    try:
        start_date = getdate(from_date)
        end_date = getdate(to_date)
        start = str(start_date) + " 00:00:00"
        end = str(end_date) + " 23:59:59"
    except Exception:
        frappe.throw("Invalid date format. Please use 'YYYY-MM-DD'.")

    # Base filters for ledger list
    filters = {"docstatus": 1, "posting_datetime": ["between", [start, end]]}
    if car_wash:
        filters["car_wash"] = car_wash
    if worker:
        filters["worker"] = worker
    if entry_type and entry_type != "All":
        filters["entry_type"] = entry_type

    rows = frappe.get_all(
        "Worker Ledger Entry",
        filters=filters,
        fields=[
            "posting_datetime",
            "worker",
            "entry_type",
            "amount",
            "company",
            "car_wash",
            "appointment",
            "note",
        ],
        order_by="posting_datetime asc, creation asc",
    )

    # Resolve worker names and roles
    worker_ids = list({r["worker"] for r in rows if r.get("worker")})
    names: dict[str, str] = {}
    roles: dict[str, str] = {}
    if worker_ids:
        for w in frappe.get_all(
            "Car wash worker",
            filters={"name": ["in", worker_ids]},
            fields=["name", "full_name", "role"],
        ):
            names[w["name"]] = w.get("full_name") or w["name"]
            roles[w["name"]] = w.get("role") or ""

    # Build SpreadsheetML XML (multiple sheets)
    output = BytesIO()
    output.write(b'<?xml version="1.0"?>\n')
    output.write(b'<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet" ')
    output.write(b'xmlns:o="urn:schemas-microsoft-com:office:office" ')
    output.write(b'xmlns:x="urn:schemas-microsoft-com:office:excel" ')
    output.write(b'xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">\n')

    # Sheet 1: Ledger
    output.write(b'<Worksheet ss:Name="Ledger">\n<Table>\n')
    headers = [
        "Дата", "Работник", "Тип", "Сумма", "Запись", "Комментарий",
    ]
    output.write(b"<Row>\n")
    for h in headers:
        output.write(f'<Cell><Data ss:Type="String">{h}</Data></Cell>\n'.encode('utf-8'))
    output.write(b"</Row>\n")

    TYPE_LABEL = {
        "Earning": "Начисление",
        "Advance": "Аванс",
        "Payout": "Выплата",
        "Correction": "Корректировка",
    }

    for r in rows:
        output.write(b"<Row>\n")
        dt = str(r.get("posting_datetime") or "")
        output.write(f'<Cell><Data ss:Type="String">{dt}</Data></Cell>\n'.encode('utf-8'))
        wname = names.get(r.get("worker"), r.get("worker") or "-")
        output.write(f'<Cell><Data ss:Type="String">{wname}</Data></Cell>\n'.encode('utf-8'))
        tlabel = TYPE_LABEL.get(r.get("entry_type"), r.get("entry_type") or "-")
        output.write(f'<Cell><Data ss:Type="String">{tlabel}</Data></Cell>\n'.encode('utf-8'))
        output.write(f'<Cell><Data ss:Type="Number">{int(r.get("amount") or 0)}</Data></Cell>\n'.encode('utf-8'))
        output.write(f'<Cell><Data ss:Type="String">{r.get("appointment") or "-"}</Data></Cell>\n'.encode('utf-8'))
        note = r.get("note") or "-"
        note = note.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        output.write(f'<Cell><Data ss:Type="String">{note}</Data></Cell>\n'.encode('utf-8'))
        output.write(b"</Row>\n")
    output.write(b"</Table>\n</Worksheet>\n")

    # Sheet 2: Earnings by day (summary)
    # create date list
    date_list = []
    cur = start_date
    while cur <= end_date:
        date_list.append(str(cur))
        cur = add_days(cur, 1)

    earning_filters = {"docstatus": 1, "entry_type": "Earning", "posting_datetime": ["between", [start, end]]}
    if car_wash:
        earning_filters["car_wash"] = car_wash
    if worker:
        earning_filters["worker"] = worker

    earning_rows = frappe.get_all(
        "Worker Ledger Entry",
        filters=earning_filters,
        fields=["worker", "amount", "posting_datetime"],
        order_by="posting_datetime asc",
    )

    # accumulate per worker/day
    per_worker: dict[str, dict[str, int]] = {}
    worker_set = set()
    for e in earning_rows:
        w = e.get("worker")
        if not w:
            continue
        d = str(getdate(str(e.get("posting_datetime"))[:10]))
        worker_set.add(w)
        per_worker.setdefault(w, {day: 0 for day in date_list})
        per_worker[w][d] += int(e.get("amount") or 0)

    # categorize by role
    washers = []
    cashiers = []
    for w in worker_set:
        (washers if roles.get(w) == "Washer" else cashiers).append(w)

    def write_section(title: str, workers: list[str]):
        output.write(b'<Row>\n')
        output.write(f'<Cell><Data ss:Type="String">{title}</Data></Cell>\n'.encode('utf-8'))
        output.write(b'</Row>\n')
        # header
        headers2 = ["#", "Работник"] + date_list + ["ИТОГО"]
        output.write(b"<Row>\n")
        for h in headers2:
            output.write(f'<Cell><Data ss:Type="String">{h}</Data></Cell>\n'.encode('utf-8'))
        output.write(b"</Row>\n")

        row_idx = 1
        for w in sorted(workers, key=lambda x: names.get(x, x)):
            out = per_worker.get(w, {day: 0 for day in date_list})
            total = sum(out.get(day, 0) for day in date_list)
            output.write(b"<Row>\n")
            output.write(f'<Cell><Data ss:Type="Number">{row_idx}</Data></Cell>\n'.encode('utf-8'))
            output.write(f'<Cell><Data ss:Type="String">{names.get(w, w)}</Data></Cell>\n'.encode('utf-8'))
            for day in date_list:
                output.write(f'<Cell><Data ss:Type="Number">{out.get(day, 0)}</Data></Cell>\n'.encode('utf-8'))
            output.write(f'<Cell><Data ss:Type="Number">{total}</Data></Cell>\n'.encode('utf-8'))
            output.write(b"</Row>\n")
            row_idx += 1

    output.write('<Worksheet ss:Name="Начисления">\n<Table>\n'.encode('utf-8'))
    write_section("Мойщики", washers)
    write_section("Кассиры", cashiers)
    output.write(b"</Table>\n</Worksheet>\n")

    # finalize workbook
    output.write(b"</Workbook>\n")

    from_str = str(start_date)
    to_str = str(end_date)
    frappe.response["type"] = "binary"
    frappe.response["filename"] = f"Ledger_{from_str}_-_{to_str}.xls"
    frappe.response["filecontent"] = output.getvalue()
    frappe.response["doctype"] = None





@frappe.whitelist()
def get_worker_period_sums(from_date: str, to_date: str,
                           car_wash: str | None = None,
                           company: str | None = None):
    """
    Возвращает суммы по типам записей за период по каждому работнику.

    Поля вывода: worker, earnings, advances, payouts
    (учитываются только проведенные записи docstatus=1 и датой в диапазоне включительно)
    """
    from frappe.utils import getdate

    try:
        start_date = getdate(from_date)
        end_date = getdate(to_date)
        start = str(start_date) + " 00:00:00"
        end = str(end_date) + " 23:59:59"
    except Exception:
        frappe.throw("Invalid date format. Please use 'YYYY-MM-DD'.")

    where = ["e.docstatus = 1", "e.posting_datetime BETWEEN %s AND %s"]
    params = [start, end]
    if car_wash:
        where.append("e.car_wash = %s")
        params.append(car_wash)
    if company:
        where.append("e.company = %s")
        params.append(company)

    sql = f"""
        SELECT
            e.worker AS worker,
            COALESCE(SUM(CASE WHEN e.entry_type = 'Earning' THEN e.amount ELSE 0 END), 0) AS earnings,
            COALESCE(SUM(CASE WHEN e.entry_type = 'Advance' THEN e.amount ELSE 0 END), 0) AS advances,
            COALESCE(SUM(CASE WHEN e.entry_type = 'Payout' THEN e.amount ELSE 0 END), 0) AS payouts
        FROM `tabWorker Ledger Entry` e
        WHERE {" AND ".join(where)}
        GROUP BY e.worker
    """

    rows = frappe.db.sql(sql, params, as_dict=True)
    return rows
