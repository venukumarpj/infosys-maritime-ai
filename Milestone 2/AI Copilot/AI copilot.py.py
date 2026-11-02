"""Step 7 additions for FreightQuote AI Copilot.

SQL-only, whitelisted question patterns 16-30. Uses the project's blocks.Q helper.
Customer results are always restricted to the authenticated customer's customer_id.
"""
import re
from blocks import Q

_TYPO_MAP = {
    "shippments": "shipments", "shipement": "shipment", "carier": "carrier",
    "carrierss": "carriers", "congeston": "congestion", "custums": "customs",
    "quots": "quotes", "cheepest": "cheapest", "delivary": "delivery",
    "arrivel": "arrival", "transist": "transit", "weigth": "weight",
}

# domain names correspond to the Step 5 role matrix.
_ALLOWED = {
    "Admin": {"quote", "shipment", "port", "carrier", "weather", "customs", "margin"},
    "Operations Manager": {"shipment", "port", "carrier", "weather", "customs"},
    "Freight Broker": {"quote", "carrier", "margin"},
    "Auditor": {"quote", "shipment", "port", "carrier", "weather", "customs", "margin"},
    "Customer": {"quote", "shipment"},
}


def answer_step7(question, role="Admin", customer_id=None):
    """Return a SQL-backed result dict or None when this is not one of intents 16-30."""
    q = re.sub(r"\s+", " ", str(question or "").lower()).strip()
    for wrong, right in _TYPO_MAP.items():
        q = re.sub(r"\b" + re.escape(wrong) + r"\b", right, q)

    is_customer = role == "Customer"
    if is_customer and not customer_id:
        return {"answer": "Your customer account is not linked yet. Please contact an administrator.",
                "sql": "", "df": None, "rows": 0}

    owner_q = " AND q.customer_id=?" if is_customer else ""
    owner_f = " AND customer_id=?" if is_customer else ""
    owner_s = (customer_id,) if is_customer else ()
    ship_owner = (" AND shipment_id IN (SELECT shipment_id FROM freight_quotes WHERE customer_id=?)"
                  if is_customer else "")
    ship_owner_s = (" AND s.shipment_id IN (SELECT shipment_id FROM freight_quotes WHERE customer_id=?)"
                    if is_customer else "")

    intents = [
        # 16 — quote volume this month
        ("quote", r"(quotes?|quotations?).*(this month|month to date)|(?:this month|month to date).*(quotes?|quotations?)",
         "SELECT COUNT(*) AS quotes_this_month FROM freight_quotes WHERE date(created_at)>=date('now','start of month')" + owner_f,
         owner_s, "Quotes created this month"),
        # 17 — carrier with most shipments
        ("carrier", r"(carrier|shipping line).*(most|maximum|highest).*(shipments?|cargo)|(most|maximum|highest).*(shipments?|cargo).*(carrier|shipping line)",
         "SELECT carrier,COUNT(*) AS shipment_count FROM shipments GROUP BY carrier ORDER BY shipment_count DESC LIMIT 10",
         (), "Carriers ranked by shipment count"),
        # 18 — destination-specific shipments
        ("shipment", r"(shipments?|cargo).*(arriv(e|ing) at|to|bound for) mumbai|mumbai.*(shipments?|arrivals?)",
         "SELECT shipment_id,origin_port,dest_port,carrier,status,eta FROM shipments WHERE dest_port LIKE ?" + ship_owner + " ORDER BY eta",
         ("%Mumbai%",) + owner_s, "Shipments arriving at Mumbai"),
        # 19 — expensive lanes, based on actual quote prices
        ("quote", r"(routes?|lanes?).*(highest|most expensive|costliest).*(freight|cost|price)|(freight|cost|price).*(highest|most expensive|costliest).*(routes?|lanes?)",
         "SELECT s.origin_port,s.dest_port,ROUND(AVG(q.final_price),2) AS average_quote_price,COUNT(*) AS quote_count FROM freight_quotes q JOIN shipments s ON s.shipment_id=q.shipment_id WHERE 1=1" + owner_q + " GROUP BY s.origin_port,s.dest_port ORDER BY average_quote_price DESC LIMIT 10",
         owner_s, "Routes ranked by average quoted freight price"),
        # 20 — average shipment weight (departure date is not in the schema)
        ("shipment", r"(average|avg|mean).*(shipment|cargo).*(weight)|(shipment|cargo).*(average|avg|mean).*(weight)",
         "SELECT ROUND(AVG(weight_kg),2) AS average_weight_kg,COUNT(*) AS shipment_count FROM shipments WHERE weight_kg IS NOT NULL" + ship_owner,
         owner_s, "Average shipment weight"),
        # 21 — in-transit shipments
        ("shipment", r"(how many|count|number of|show|list).*(shipments?).*(in transit)|(in transit).*(shipments?|how many|count)",
         "SELECT shipment_id,origin_port,dest_port,carrier,status,eta FROM shipments WHERE lower(status) LIKE '%transit%'" + ship_owner + " ORDER BY eta",
         owner_s, "Shipments currently in transit"),
        # 22 — margin above 20%
        ("margin", r"(quotes?|margins?).*(above|over|greater than|more than)\s*20\s*%|(?:above|over|greater than|more than)\s*20\s*%.*(margin|quotes?)",
         "SELECT quote_id,shipment_id,carrier,final_price,margin_pct,status,created_at FROM freight_quotes WHERE margin_pct>20" + owner_f + " ORDER BY margin_pct DESC",
         owner_s, "Quotes with margin above 20 percent"),
        # 23 — highest-risk carriers
        ("carrier", r"(carrier|shipping line).*(highest|most|maximum).*(risk)|(highest|most|maximum).*(risk).*(carrier|shipping line)",
         "SELECT name AS carrier,rating,on_time_pct,avg_cost_index,risk_level FROM carriers ORDER BY CASE lower(risk_level) WHEN 'critical' THEN 4 WHEN 'high' THEN 3 WHEN 'medium' THEN 2 WHEN 'low' THEN 1 ELSE 0 END DESC,avg_cost_index DESC LIMIT 10",
         (), "Carriers ranked by risk level"),
        # 24 — weather affected destinations
        ("weather", r"(shipments?|cargo).*(bad weather|weather affected|weather risk|storm)|(?:bad weather|weather affected|weather risk|storm).*(shipments?|cargo)",
         "SELECT s.shipment_id,s.origin_port,s.dest_port,s.carrier,s.status,w.current_severity,w.forecast,w.wind_speed,w.wave_height FROM shipments s JOIN weather_risks w ON lower(w.port_name)=lower(s.dest_port) WHERE w.current_severity>=3" + ship_owner_s + " ORDER BY w.current_severity DESC,w.wind_speed DESC",
         owner_s, "Shipments whose destination has elevated weather severity"),
        # 25 — customs holds by destination
        ("customs", r"(destination|port|where).*(most|highest|many).*(customs hold|held)|(?:customs hold|held).*(destination|port|most|highest)",
         "SELECT dest_port,COUNT(*) AS customs_hold_count FROM shipments WHERE status='Customs Hold'" + ship_owner + " GROUP BY dest_port ORDER BY customs_hold_count DESC",
         owner_s, "Customs holds grouped by destination"),
        # 26 — pending quotes
        ("quote", r"(how many|count|number of|show|list).*(quotes?).*(pending|awaiting)|(pending|awaiting).*(quotes?)",
         "SELECT quote_id,shipment_id,carrier,final_price,margin_pct,status,created_at FROM freight_quotes WHERE lower(status) LIKE '%pending%'" + owner_f + " ORDER BY created_at DESC",
         owner_s, "Quotes with a pending status"),
        # 27 — cheapest lanes by average quote price
        ("quote", r"(cheapest|lowest cost|least expensive).*(route|lane)|(route|lane).*(cheapest|lowest cost|least expensive)",
         "SELECT s.origin_port,s.dest_port,ROUND(AVG(q.final_price),2) AS average_quote_price,COUNT(*) AS quote_count FROM freight_quotes q JOIN shipments s ON s.shipment_id=q.shipment_id WHERE 1=1" + owner_q + " GROUP BY s.origin_port,s.dest_port ORDER BY average_quote_price ASC LIMIT 10",
         owner_s, "Routes ranked by average quoted price"),
        # 28 — overdue shipments
        ("shipment", r"(overdue|past due|late delivery|exceeded).*(shipment|delivery|eta)|(shipment|delivery).*(overdue|past due|late|exceeded|expected delivery)",
         "SELECT shipment_id,origin_port,dest_port,carrier,status,eta FROM shipments WHERE date(eta)<date('now') AND lower(status) NOT LIKE '%deliver%'" + ship_owner + " ORDER BY eta",
         owner_s, "Shipments past ETA that are not marked delivered"),
        # 29 — cleared customs
        ("customs", r"(customs|shipment).*(cleared|clearance complete|released)|(?:cleared|clearance complete|released).*(customs|shipment)",
         "SELECT shipment_id,origin_port,dest_port,carrier,status,eta FROM shipments WHERE (lower(status) LIKE '%custom%clear%' OR lower(status) LIKE '%clearance complete%' OR lower(status) LIKE '%released%')" + ship_owner + " ORDER BY eta",
         owner_s, "Shipments with a customs-cleared or released status"),
        # 30 — total value of quotes
        ("quote", r"(total|combined|overall|sum).*(value|amount|price).*(quotes?)|(quotes?).*(total|combined|overall|sum).*(value|amount|price)",
         "SELECT COUNT(*) AS quote_count,ROUND(COALESCE(SUM(final_price),0),2) AS total_quote_value FROM freight_quotes WHERE 1=1" + owner_f,
         owner_s, "Total value of generated freight quotes"),
    ]

    for domain, pattern, sql, params, label in intents:
        if not re.search(pattern, q):
            continue
        if domain not in _ALLOWED.get(role, set()):
            return {"answer": "Your role does not have permission to view this category of Copilot data.",
                    "sql": "", "df": None, "rows": 0}
        try:
            df = Q(sql, params)
            n = len(df)
            if n == 0:
                answer = f"No matching records were found for: {label.lower()}."
            else:
                answer = f"**{label}** — {n} row(s) returned from the FreightQuote database."
            return {"answer": answer, "sql": sql, "df": df, "rows": n, "row_count": n}
        except Exception as exc:
            # Do not expose SQL errors or schema details to end users.
            return {"answer": "I recognized your question, but the database could not complete that query. Please try again or contact the project administrator.",
                    "sql": sql, "df": None, "rows": 0, "row_count": 0, "error": str(exc)}
    return None
