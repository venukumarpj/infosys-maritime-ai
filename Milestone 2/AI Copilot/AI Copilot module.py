"""FreightQuote AI Copilot: 30 SQL-only question patterns.

Standalone Step 7 module (apart from the project's existing blocks.Q database helper).
- Questions 1-15: core FreightQuote questions.
- Questions 16-30: additional Step 7 questions.
- Uses parameterized SQL, role checks, and customer_id filtering.

Integration: place this file beside blocks.py and import `answer_copilot` in server.py.
This module does not create or seed the database; the project must initialize its Freight DB.
"""
import re
from blocks import Q

_ALLOWED = {
    "Admin": {"quote", "shipment", "port", "carrier", "weather", "customs", "margin", "customer"},
    "Operations Manager": {"shipment", "port", "carrier", "weather", "customs"},
    "Freight Broker": {"quote", "carrier", "margin"},
    "Auditor": {"quote", "shipment", "port", "carrier", "weather", "customs", "margin", "customer"},
    "Customer": {"quote", "shipment"},
}

_TYPO_MAP = {
    "shippments": "shipments", "shipement": "shipment", "carier": "carrier",
    "carrierss": "carriers", "congeston": "congestion", "custums": "customs",
    "quots": "quotes", "cheepest": "cheapest", "delivary": "delivery",
    "arrivel": "arrival", "transist": "transit", "weigth": "weight",
    "wether": "weather", "portss": "ports", "margn": "margin",
}

SUGGESTIONS = [
    "Show all shipments.",
    "Which ports are most congested?",
    "Show all freight quotes.",
]


def _normalise(question):
    q = re.sub(r"\s+", " ", str(question or "").lower()).strip()
    for wrong, right in _TYPO_MAP.items():
        q = re.sub(r"\b" + re.escape(wrong) + r"\b", right, q)
    return q


def answer_copilot(question, role="Customer", customer_id=None):
    """Return a SQL-backed response dict for one of 30 intents, else a polite fallback.

    Dict fields: answer, sql, df, rows, row_count, suggestions.
    `None` is not returned: unmatched questions receive the required out-of-scope reply.
    """
    q = _normalise(question)
    is_customer = role == "Customer"
    if is_customer and not customer_id:
        return {"answer": "Your customer account is not linked yet. Please contact an administrator.",
                "sql": "", "df": None, "rows": 0, "row_count": 0}

    # These SQL fragments restrict Customer users to their own records.
    quote_filter = " AND customer_id=?" if is_customer else ""
    quote_params = (customer_id,) if is_customer else ()
    shipment_filter = (" AND shipment_id IN (SELECT shipment_id FROM freight_quotes WHERE customer_id=?)"
                       if is_customer else "")
    shipment_params = (customer_id,) if is_customer else ()
    joined_shipment_filter = (" AND s.shipment_id IN (SELECT shipment_id FROM freight_quotes WHERE customer_id=?)"
                              if is_customer else "")

    # Each entry: domain, regex, SQL, parameters, human-readable label.
    intents = [
        # 1-15: core question patterns
        ("shipment", r"\b(show|list|display)\b.*\b(all )?(shipments?|cargo)\b|\ball shipments\b",
         "SELECT shipment_id,origin_port,dest_port,carrier,status,eta,weight_kg,predicted_delay_risk FROM shipments WHERE 1=1" + shipment_filter + " ORDER BY eta",
         shipment_params, "All shipments"),
        ("shipment", r"\b(how many|count|number of)\b.*\bshipments?\b",
         "SELECT COUNT(*) AS shipment_count FROM shipments WHERE 1=1" + shipment_filter,
         shipment_params, "Shipment count"),
        ("shipment", r"\b(show|list|find)\b.*\b(delayed|late)\b.*\bshipments?\b|\b(delayed|late) shipments\b",
         "SELECT shipment_id,origin_port,dest_port,carrier,status,eta,predicted_delay_risk FROM shipments WHERE (lower(status) LIKE '%delay%' OR lower(status) LIKE '%late%')" + shipment_filter + " ORDER BY eta",
         shipment_params, "Delayed shipments"),
        ("shipment", r"\b(highest|top|greatest)\b.*\b(delay )?risk\b|\b(delay )?risk\b.*\b(highest|top)\b",
         "SELECT shipment_id,origin_port,dest_port,carrier,status,eta,predicted_delay_risk FROM shipments WHERE 1=1" + shipment_filter + " ORDER BY predicted_delay_risk DESC LIMIT 10",
         shipment_params, "Shipments with highest predicted delay risk"),
        ("quote", r"\b(show|list|display)\b.*\b(all )?(freight )?quotes?\b|\ball freight quotes\b",
         "SELECT quote_id,shipment_id,customer_id,carrier,final_price,margin_pct,status FROM freight_quotes WHERE 1=1" + quote_filter + " ORDER BY quote_id DESC",
         quote_params, "All freight quotes"),
        ("quote", r"\b(total|sum|overall)\b.*\b(value|amount|price)\b.*\b(quotes?)\b|\b(quotes?)\b.*\b(total|sum)\b.*\b(value|amount|price)\b",
         "SELECT COUNT(*) AS quote_count,ROUND(COALESCE(SUM(final_price),0),2) AS total_quote_value FROM freight_quotes WHERE 1=1" + quote_filter,
         quote_params, "Total freight quote value"),
        ("margin", r"\b(low|poor|small)\b.*\b(margin|margins)\b|\b(quotes?)\b.*\b(low|below)\b.*\bmargin\b",
         "SELECT quote_id,shipment_id,carrier,final_price,margin_pct,status FROM freight_quotes WHERE margin_pct<10" + quote_filter + " ORDER BY margin_pct",
         quote_params, "Quotes with margins below 10 percent"),
        ("carrier", r"\b(best|highest)\b.*\b(on.?time|punctuality)\b.*\b(carrier|shipping line)\b|\b(carrier|shipping line)\b.*\b(best|highest)\b.*\b(on.?time|punctuality)\b",
         "SELECT name,rating,on_time_pct,avg_cost_index,risk_level FROM carriers ORDER BY on_time_pct DESC LIMIT 10",
         (), "Carriers ranked by on-time performance"),
        ("carrier", r"\b(lowest|cheapest|least)\b.*\b(cost|cost index)\b.*\b(carrier|shipping line)\b|\b(carrier|shipping line)\b.*\b(lowest|cheapest)\b.*\bcost\b",
         "SELECT name,rating,on_time_pct,avg_cost_index,risk_level FROM carriers ORDER BY avg_cost_index ASC LIMIT 10",
         (), "Carriers ranked by cost index"),
        ("port", r"\b(most|highest|top)\b.*\b(congested|congestion)\b.*\bports?\b|\bports?\b.*\b(most|highest|top)\b.*\b(congested|congestion)\b",
         "SELECT port_name,country,region,congestion_index,avg_dwell_days FROM ports ORDER BY congestion_index DESC LIMIT 10",
         (), "Most congested ports"),
        ("port", r"\b(highest|longest|maximum)\b.*\b(dwell time|dwell)\b|\b(dwell time|dwell)\b.*\b(highest|longest)\b",
         "SELECT port_name,country,region,congestion_index,avg_dwell_days FROM ports ORDER BY avg_dwell_days DESC LIMIT 10",
         (), "Ports with highest average dwell time"),
        ("weather", r"\b(show|list|current)\b.*\b(weather risks?|storms?|weather conditions?)\b|\b(weather risks?|storms?)\b",
         "SELECT port_name,current_severity,forecast,wind_speed,wave_height FROM weather_risks ORDER BY current_severity DESC",
         (), "Current weather risks"),
        ("weather", r"\b(high|severe|highest)\b.*\b(weather )?risk\b.*\bports?\b|\bports?\b.*\b(high|severe)\b.*\bweather risk\b",
         "SELECT port_name,current_severity,forecast,wind_speed,wave_height FROM weather_risks WHERE current_severity>=3 ORDER BY current_severity DESC",
         (), "Ports with high weather risk"),
        ("customs", r"\b(show|list|display)\b.*\bcustoms rules?\b|\bcustoms rules?\b",
         "SELECT chapter,goods,duty_pct,docs,restricted FROM customs_rules ORDER BY chapter",
         (), "Customs rules"),
        ("customer", r"\b(show|list|display)\b.*\b(all )?customers?\b|\ball customers\b",
         "SELECT customer_id,name,industry,priority_tier,credit_risk FROM customers ORDER BY name",
         (), "Customers"),

        # 16-30: additional Step 7 question patterns
        ("quote", r"(quotes?|quotations?).*(this month|month to date)|(?:this month|month to date).*(quotes?|quotations?)",
         "SELECT COUNT(*) AS quotes_this_month FROM freight_quotes WHERE date(created_at)>=date('now','start of month')" + quote_filter,
         quote_params, "Quotes created this month"),
        ("carrier", r"(carrier|shipping line).*(most|maximum|highest).*(shipments?|cargo)|(most|maximum|highest).*(shipments?|cargo).*(carrier|shipping line)",
         "SELECT carrier,COUNT(*) AS shipment_count FROM shipments GROUP BY carrier ORDER BY shipment_count DESC LIMIT 10",
         (), "Carriers ranked by shipment count"),
        ("shipment", r"(shipments?|cargo).*(arriv(e|ing) at|to|bound for) mumbai|mumbai.*(shipments?|arrivals?)",
         "SELECT shipment_id,origin_port,dest_port,carrier,status,eta FROM shipments WHERE dest_port LIKE ?" + shipment_filter + " ORDER BY eta",
         ("%Mumbai%",) + shipment_params, "Shipments arriving at Mumbai"),
        ("quote", r"(routes?|lanes?).*(highest|most expensive|costliest).*(freight|cost|price)|(freight|cost|price).*(highest|most expensive|costliest).*(routes?|lanes?)",
         "SELECT s.origin_port,s.dest_port,ROUND(AVG(q.final_price),2) AS average_quote_price,COUNT(*) AS quote_count FROM freight_quotes q JOIN shipments s ON s.shipment_id=q.shipment_id WHERE 1=1" + (" AND q.customer_id=?" if is_customer else "") + " GROUP BY s.origin_port,s.dest_port ORDER BY average_quote_price DESC LIMIT 10",
         quote_params, "Routes ranked by average quoted freight price"),
        ("shipment", r"(average|avg|mean).*(shipment|cargo).*(weight)|(shipment|cargo).*(average|avg|mean).*(weight)",
         "SELECT ROUND(AVG(weight_kg),2) AS average_weight_kg,COUNT(*) AS shipment_count FROM shipments WHERE weight_kg IS NOT NULL" + shipment_filter,
         shipment_params, "Average shipment weight"),
        ("shipment", r"(how many|count|number of|show|list).*(shipments?).*(in transit)|(in transit).*(shipments?|how many|count)",
         "SELECT shipment_id,origin_port,dest_port,carrier,status,eta FROM shipments WHERE lower(status) LIKE '%transit%'" + shipment_filter + " ORDER BY eta",
         shipment_params, "Shipments currently in transit"),
        ("margin", r"(quotes?|margins?).*(above|over|greater than|more than)\s*20\s*%|(?:above|over|greater than|more than)\s*20\s*%.*(margin|quotes?)",
         "SELECT quote_id,shipment_id,carrier,final_price,margin_pct,status FROM freight_quotes WHERE margin_pct>20" + quote_filter + " ORDER BY margin_pct DESC",
         quote_params, "Quotes with margin above 20 percent"),
        ("carrier", r"(carrier|shipping line).*(highest|most|maximum).*(risk)|(highest|most|maximum).*(risk).*(carrier|shipping line)",
         "SELECT name AS carrier,rating,on_time_pct,avg_cost_index,risk_level FROM carriers ORDER BY CASE lower(risk_level) WHEN 'critical' THEN 4 WHEN 'high' THEN 3 WHEN 'medium' THEN 2 WHEN 'low' THEN 1 ELSE 0 END DESC,avg_cost_index DESC LIMIT 10",
         (), "Carriers ranked by risk level"),
        ("weather", r"(shipments?|cargo).*(bad weather|weather affected|weather risk|storm)|(?:bad weather|weather affected|weather risk|storm).*(shipments?|cargo)",
         "SELECT s.shipment_id,s.origin_port,s.dest_port,s.carrier,s.status,w.current_severity,w.forecast,w.wind_speed,w.wave_height FROM shipments s JOIN weather_risks w ON lower(w.port_name)=lower(s.dest_port) WHERE w.current_severity>=3" + joined_shipment_filter + " ORDER BY w.current_severity DESC,w.wind_speed DESC",
         shipment_params, "Shipments whose destination has elevated weather severity"),
        ("customs", r"(destination|port|where).*(most|highest|many).*(customs hold|held)|(?:customs hold|held).*(destination|port|most|highest)",
         "SELECT dest_port,COUNT(*) AS customs_hold_count FROM shipments WHERE status='Customs Hold'" + shipment_filter + " GROUP BY dest_port ORDER BY customs_hold_count DESC",
         shipment_params, "Customs holds grouped by destination"),
        ("quote", r"(how many|count|number of|show|list).*(quotes?).*(pending|awaiting)|(pending|awaiting).*(quotes?)",
         "SELECT quote_id,shipment_id,carrier,final_price,margin_pct,status FROM freight_quotes WHERE lower(status) LIKE '%pending%'" + quote_filter + " ORDER BY quote_id DESC",
         quote_params, "Quotes with a pending status"),
        ("quote", r"(cheapest|lowest cost|least expensive).*(route|lane)|(route|lane).*(cheapest|lowest cost|least expensive)",
         "SELECT s.origin_port,s.dest_port,ROUND(AVG(q.final_price),2) AS average_quote_price,COUNT(*) AS quote_count FROM freight_quotes q JOIN shipments s ON s.shipment_id=q.shipment_id WHERE 1=1" + (" AND q.customer_id=?" if is_customer else "") + " GROUP BY s.origin_port,s.dest_port ORDER BY average_quote_price ASC LIMIT 10",
         quote_params, "Routes ranked by average quoted price"),
        ("shipment", r"(overdue|past due|late delivery|exceeded).*(shipment|delivery|eta)|(shipment|delivery).*(overdue|past due|late|exceeded|expected delivery)",
         "SELECT shipment_id,origin_port,dest_port,carrier,status,eta FROM shipments WHERE date(eta)<date('now') AND lower(status) NOT LIKE '%deliver%'" + shipment_filter + " ORDER BY eta",
         shipment_params, "Shipments past ETA that are not marked delivered"),
        ("customs", r"(customs|shipment).*(cleared|clearance complete|released)|(?:cleared|clearance complete|released).*(customs|shipment)",
         "SELECT shipment_id,origin_port,dest_port,carrier,status,eta FROM shipments WHERE (lower(status) LIKE '%custom%clear%' OR lower(status) LIKE '%clearance complete%' OR lower(status) LIKE '%released%')" + shipment_filter + " ORDER BY eta",
         shipment_params, "Shipments with a customs-cleared or released status"),
        ("quote", r"(total|combined|overall|sum).*(value|amount|price).*(quotes?)|(quotes?).*(total|combined|overall|sum).*(value|amount|price)",
         "SELECT COUNT(*) AS quote_count,ROUND(COALESCE(SUM(final_price),0),2) AS total_quote_value FROM freight_quotes WHERE 1=1" + quote_filter,
         quote_params, "Total value of generated freight quotes"),
    ]

    for domain, pattern, sql, params, label in intents:
        if not re.search(pattern, q):
            continue
        if domain not in _ALLOWED.get(role, set()):
            return {"answer": "Your role does not have permission to view this category of Copilot data.",
                    "sql": "", "df": None, "rows": 0, "row_count": 0}
        try:
            df = Q(sql, params)
            count = len(df.index)
            answer = (f"No matching records were found for: {label.lower()}." if count == 0
                      else f"{label}: {count} row(s) returned from the FreightQuote database.")
            return {"answer": answer, "sql": sql, "df": df, "rows": count,
                    "row_count": count, "intent": label}
        except Exception as exc:
            # Keep internal database details out of the user-facing answer.
            return {"answer": "I recognized your question, but the database could not complete it. Please check the database setup or contact the project administrator.",
                    "sql": sql, "df": None, "rows": 0, "row_count": 0,
                    "intent": label, "error": str(exc)}

    return {"answer": "Sorry, I can answer questions about FreightQuote shipments, quotes, carriers, ports, weather, customs and customers. Try one of these questions:",
            "sql": "", "df": None, "rows": 0, "row_count": 0,
            "suggestions": SUGGESTIONS}


# Backward-compatible name for the earlier Step 7 helper.
def answer_step7(question, role="Customer", customer_id=None):
    return answer_copilot(question, role=role, customer_id=customer_id)
