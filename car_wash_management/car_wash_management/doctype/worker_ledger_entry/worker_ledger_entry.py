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
        # Разрешаем отрицательные суммы только для Correction, иначе требуем > 0
        if self.entry_type != "Correction" and self.amount <= 0:
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
                WHEN e.entry_type = 'Correction' THEN e.amount
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
    from frappe.utils import getdate, add_days, add_months

    def _parse_dates(fd: str, td: str):
        try:
            sd = getdate(fd)
            ed = getdate(td)
            return sd, ed, str(sd) + " 00:00:00", str(ed) + " 23:59:59"
        except Exception:
            frappe.throw("Invalid date format. Please use 'YYYY-MM-DD'.")

    def _ensure_period_limit(sd, ed):
        # Require ed <= add_months(sd, 3)
        limit = add_months(sd, 3)
        if ed > limit:
            frappe.throw("Максимальный период выгрузки — 3 месяца.")

    def _build_ledger_filters(start_ts: str, end_ts: str):
        base = {"docstatus": 1, "posting_datetime": ["between", [start_ts, end_ts]]}
        if car_wash:
            base["car_wash"] = car_wash
        if worker:
            base["worker"] = worker
        if entry_type and entry_type != "All":
            base["entry_type"] = entry_type
        return base

    def _fetch_workers_info(worker_ids_list: list[str]):
        names_map: dict[str, str] = {}
        roles_map: dict[str, str] = {}
        if worker_ids_list:
            for w in frappe.get_all(
                "Car wash worker",
                filters={"name": ["in", worker_ids_list]},
                fields=["name", "full_name", "role"],
            ):
                names_map[w["name"]] = w.get("full_name") or w["name"]
                roles_map[w["name"]] = w.get("role") or ""
        return names_map, roles_map

    def _xml_escape(value: str) -> str:
        if value is None:
            return "-"
        s = str(value)
        s = s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        return s

    def _wb_start() -> BytesIO:
        out = BytesIO()
        out.write(b'<?xml version="1.0"?>\n')
        out.write(b'<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet" ')
        out.write(b'xmlns:o="urn:schemas-microsoft-com:office:office" ')
        out.write(b'xmlns:x="urn:schemas-microsoft-com:office:excel" ')
        out.write(b'xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">\n')
        return out

    def _ws_start(out: BytesIO, name: str):
        out.write(f'<Worksheet ss:Name="{_xml_escape(name)}">\n<Table>\n'.encode('utf-8'))

    def _ws_end(out: BytesIO):
        out.write(b"</Table>\n</Worksheet>\n")

    def _row(out: BytesIO, cells: list[tuple[str, str | int]]):
        out.write(b"<Row>\n")
        for cell_type, value in cells:
            if cell_type == "Number":
                out.write(f'<Cell><Data ss:Type="Number">{int(value or 0)}</Data></Cell>\n'.encode('utf-8'))
            else:
                out.write(f'<Cell><Data ss:Type="String">{_xml_escape(value)}</Data></Cell>\n'.encode('utf-8'))
        out.write(b"</Row>\n")

    # 1) Prepare dates and filters
    start_date, end_date, start_ts, end_ts = _parse_dates(from_date, to_date)
    ledger_filters = _build_ledger_filters(start_ts, end_ts)
    _ensure_period_limit(start_date, end_date)

    # 2) Fetch ledger rows
    rows = frappe.get_all(
        "Worker Ledger Entry",
        filters=ledger_filters,
        fields=[
            "posting_datetime",
            "worker",
            "entry_type",
            "amount",
            "company",
            "car_wash",
            "appointment",
            "note",
            "owner",
            "modified_by",
        ],
        order_by="posting_datetime asc, creation asc",
    )

    # 3) Resolve worker names and roles
    worker_ids = list({r["worker"] for r in rows if r.get("worker")})
    names, roles = _fetch_workers_info(worker_ids)

    # 4) Build workbook and sheets
    output = _wb_start()

    TYPE_LABEL = {
        "Earning": "Начисление",
        "Advance": "Аванс",
        "Payout": "Выплата",
        "Correction": "Корректировка",
    }

    # Sheet 2 and 3: Per-day summaries (Начисления, Авансы)
    def _write_summary_sheet(sheet_title: str, entry_type_key: str):
        # dates list
        date_list = []
        cur = start_date
        while cur <= end_date:
            date_list.append(str(cur))
            cur = add_days(cur, 1)

        flt = {"docstatus": 1, "entry_type": entry_type_key, "posting_datetime": ["between", [start_ts, end_ts]]}
        if car_wash:
            flt["car_wash"] = car_wash
        if worker:
            flt["worker"] = worker

        rows2 = frappe.get_all(
            "Worker Ledger Entry",
            filters=flt,
            fields=["worker", "amount", "posting_datetime"],
            order_by="posting_datetime asc",
        )

        per_worker: dict[str, dict[str, int]] = {}
        worker_set = set()
        for e in rows2:
            w = e.get("worker")
            if not w:
                continue
            d = str(getdate(str(e.get("posting_datetime"))[:10]))
            worker_set.add(w)
            per_worker.setdefault(w, {day: 0 for day in date_list})
            per_worker[w][d] += int(e.get("amount") or 0)

        # ensure names/roles contain all workers met in this sheet
        missing_ids = [wid for wid in worker_set if wid not in names]
        if missing_ids:
            extra_names, extra_roles = _fetch_workers_info(missing_ids)
            names.update(extra_names)
            roles.update(extra_roles)

        washers: list[str] = []
        cashiers: list[str] = []
        for w in worker_set:
            (washers if roles.get(w) == "Washer" else cashiers).append(w)

        def write_section(title: str, workers_list: list[str]):
            _row(output, [("String", title)])
            headers2 = [("String", "#"), ("String", "Работник")] + [("String", d) for d in date_list] + [("String", "ИТОГО")]
            _row(output, headers2)

            row_idx = 1
            for wid in sorted(workers_list, key=lambda x: names.get(x, x)):
                out = per_worker.get(wid, {day: 0 for day in date_list})
                total = sum(out.get(day, 0) for day in date_list)
                row_cells: list[tuple[str, str | int]] = [("Number", row_idx), ("String", names.get(wid, wid))]
                for day in date_list:
                    row_cells.append(("Number", out.get(day, 0)))
                row_cells.append(("Number", total))
                _row(output, row_cells)
                row_idx += 1

        _ws_start(output, sheet_title)
        write_section("Мойщики", washers)
        write_section("Кассиры", cashiers)
        _ws_end(output)

    _write_summary_sheet("Начисления", "Earning")
    _write_summary_sheet("Авансы", "Advance")
    _write_summary_sheet("Выплаты", "Payout")
    _write_summary_sheet("Корректировки", "Correction")

    # Sheet: Баланс (net per day)
    def _write_balance_sheet(sheet_title: str = "Баланс"):
        # dates list
        date_list = []
        cur = start_date
        while cur <= end_date:
            date_list.append(str(cur))
            cur = add_days(cur, 1)

        flt = {"docstatus": 1, "posting_datetime": ["between", [start_ts, end_ts]]}
        if car_wash:
            flt["car_wash"] = car_wash
        if worker:
            flt["worker"] = worker

        rows2 = frappe.get_all(
            "Worker Ledger Entry",
            filters=flt,
            fields=["worker", "entry_type", "amount", "posting_datetime"],
            order_by="posting_datetime asc",
        )

        per_worker: dict[str, dict[str, int]] = {}
        worker_set = set()
        for e in rows2:
            w = e.get("worker")
            if not w:
                continue
            d = str(getdate(str(e.get("posting_datetime"))[:10]))
            worker_set.add(w)
            per_worker.setdefault(w, {day: 0 for day in date_list})
            sign = ENTRY_SIGN.get(e.get("entry_type"), 1)
            per_worker[w][d] += sign * int(e.get("amount") or 0)

        # ensure names/roles contain all workers met in this sheet
        missing_ids = [wid for wid in worker_set if wid not in names]
        if missing_ids:
            extra_names, extra_roles = _fetch_workers_info(missing_ids)
            names.update(extra_names)
            roles.update(extra_roles)

        washers: list[str] = []
        cashiers: list[str] = []
        for w in worker_set:
            (washers if roles.get(w) == "Washer" else cashiers).append(w)

        def write_section(title: str, workers_list: list[str]):
            _row(output, [("String", title)])
            headers2 = [("String", "#"), ("String", "Работник")] + [("String", d) for d in date_list] + [("String", "ИТОГО")]
            _row(output, headers2)

            row_idx = 1
            for wid in sorted(workers_list, key=lambda x: names.get(x, x)):
                out = per_worker.get(wid, {day: 0 for day in date_list})
                total = sum(out.get(day, 0) for day in date_list)
                row_cells: list[tuple[str, str | int]] = [("Number", row_idx), ("String", names.get(wid, wid))]
                for day in date_list:
                    row_cells.append(("Number", out.get(day, 0)))
                row_cells.append(("Number", total))
                _row(output, row_cells)
                row_idx += 1

        _ws_start(output, sheet_title)
        write_section("Мойщики", washers)
        write_section("Кассиры", cashiers)
        _ws_end(output)

    _write_balance_sheet("Баланс")

    # Sheet last: Operations (renamed Ledger)
    _ws_start(output, "Операции")
    _row(output, [("String", "Дата"), ("String", "Работник"), ("String", "Тип"), ("String", "Сумма"), ("String", "Запись"), ("String", "Комментарий"), ("String", "Автор")])
    for r in rows:
        dt = str(r.get("posting_datetime") or "")
        wname = names.get(r.get("worker"), r.get("worker") or "-")
        tlabel = TYPE_LABEL.get(r.get("entry_type"), r.get("entry_type") or "-")
        amount = int(r.get("amount") or 0)
        appointment = r.get("appointment") or "-"
        note = r.get("note") or "-"
        author = r.get("modified_by") or r.get("owner") or "-"
        _row(output, [
            ("String", dt),
            ("String", wname),
            ("String", tlabel),
            ("Number", amount),
            ("String", appointment),
            ("String", note),
            ("String", author),
        ])
    _ws_end(output)

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
