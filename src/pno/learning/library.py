"""Built-in retail learning content, so full courses can be made with no AI at all.

Each topic is a module: lessons made of blocks (text, points, formula, example, chart, kpis, steps, table, dodont,
callout) plus quiz questions (mcq, tf, calc, scenario) with answers and explanations. Figures in examples are
illustrative, chosen to be realistic for a Pakistani hypermarket, and are labelled as examples.
"""

from __future__ import annotations

from typing import Any

T = dict[str, Any]


def P(text: str) -> T:
    return {"type": "para", "text": text}


def B(*items: str, title: str = "") -> T:
    return {"type": "points", "title": title, "items": list(items)}


def F(name: str, expr: str, where: list[str], example: str = "") -> T:
    return {"type": "formula", "name": name, "expr": expr, "where": where, "example": example}


def EX(title: str, *lines: str) -> T:
    return {"type": "example", "title": title, "lines": list(lines)}


def CH(kind: str, title: str, labels: list, series: list[tuple[str, list]], unit: str = "") -> T:
    return {"type": "chart", "kind": kind, "title": title, "labels": labels,
            "series": [{"name": n, "values": v} for n, v in series], "unit": unit}


def K(*items: tuple[str, str, str]) -> T:
    return {"type": "kpis", "items": [{"label": a, "value": b, "sub": c} for a, b, c in items]}


def ST(title: str, *steps: str) -> T:
    return {"type": "steps", "title": title, "items": list(steps)}


def TB(title: str, columns: list[str], rows: list[list]) -> T:
    return {"type": "table", "title": title, "columns": columns, "rows": rows}


def DD(do: list[str], dont: list[str]) -> T:
    return {"type": "dodont", "do": do, "dont": dont}


def C(kind: str, text: str) -> T:
    return {"type": "callout", "kind": kind, "text": text}


def MCQ(q: str, options: list[str], answer: int, explain: str) -> T:
    return {"type": "mcq", "q": q, "options": options, "answer": answer, "explain": explain}


def TF(q: str, answer: bool, explain: str) -> T:
    return {"type": "tf", "q": q, "options": ["True", "False"], "answer": 0 if answer else 1, "explain": explain}


def CALC(q: str, answer: str, explain: str) -> T:
    return {"type": "calc", "q": q, "answer": answer, "explain": explain}


def SC(q: str, answer: str, explain: str) -> T:
    return {"type": "scenario", "q": q, "answer": answer, "explain": explain}


TOPICS: dict[str, T] = {}


def topic(key: str, title: str, roles: list[int], skills: list[str], summary: str, lessons: list[T], quiz: list[T], activity: str) -> None:
    TOPICS[key] = {"key": key, "title": title, "roles": roles, "skills": skills, "summary": summary, "lessons": lessons, "quiz": quiz,
                   "activity": activity}


# ------------------------------------------------------------------------------------------------ shrink
topic("shrink", "Shrinkage and waste control", [1, 2, 3, 4, 6], ["Shrink & loss prevention", "Fresh food"],
      "What shrink is, how it is measured, where it comes from and the daily habits that cut it.", [
    {"title": "What shrinkage is and why it matters", "minutes": 20, "objectives": [
        "Define shrinkage and its two parts, known and unknown", "Explain why 1% of shrink costs far more than it looks"],
     "blocks": [
        P("Shrinkage is stock we paid for but never sold. It shows up as the difference between what the system says we should have "
          "and what we really have, plus everything we write off (waste, damages, expiries)."),
        B("Known shrink: recorded waste, damages, expiries, markdown losses, samples.",
          "Unknown shrink: found only at stock count: theft, wrong receiving, scanning and pricing errors, admin mistakes.", title="Two parts"),
        F("Shrink %", "Shrink value ÷ Net sales × 100", ["Shrink value at cost price", "Net sales for the same period"],
          "Rs 450,000 shrink on Rs 30,000,000 sales = 1.5%"),
        EX("Why 1.5% hurts", "A section sells Rs 30 M a month at a 20% gross margin, so it earns Rs 6 M.",
           "Shrink of 1.5% = Rs 450,000: that is 7.5% of the whole month's margin gone.",
           "To earn that Rs 450,000 back we must sell an extra Rs 2.25 M at 20% margin."),
        CH("bar", "Example: where a fresh section's shrink comes from (%)", ["Expiry", "Damage", "Unknown", "Markdowns", "Admin errors"],
           [("Share of shrink", [38, 17, 24, 13, 8])], "%"),
        C("key", "Shrink is a margin problem first: every rupee of shrink comes straight off profit."),
    ]},
    {"title": "Finding the causes", "minutes": 25, "objectives": ["Read a shrink report by section and reason", "Pick the three biggest causes to act on"],
     "blocks": [
        P("Start with the numbers, not opinions. Rank sections by shrink value (not only %), then look at reasons and items."),
        ST("Five steps to diagnose shrink", "Rank sections by shrink value vs budget", "Split each section by reason code",
           "List the top 20 items by loss value", "Walk the floor: check displays, dates, backroom, receiving",
           "Agree 3 actions with owners and dates"),
        TB("Example: top items in a bakery (one week)", ["Item", "Loss (Rs)", "Main reason", "Action"], [
            ["Croissant 4-pack", "18,400", "Expiry", "Cut bake quantity after 6pm"], ["Cream cake", "12,900", "Damage", "Train handling, new trays"],
            ["Brown bread", "9,700", "Expiry", "Mark down at 7pm, not 9pm"], ["Donut box", "6,200", "Unknown", "Check scanning at till"]]),
        C("tip", "80/20 rule: usually about 20% of items cause about 80% of the loss. Fix those first."),
    ]},
    {"title": "Daily habits that cut shrink", "minutes": 25, "objectives": ["Apply FIFO and FEFO on every fill", "Run a correct markdown"],
     "blocks": [
        B("FIFO: first in, first out. Older stock goes to the front.", "FEFO: first expired, first out. For dated goods, the earliest date sells first.",
          "Order to the plan: do not over-order to 'be safe'.", "Record every write-off the same day with the right reason.", title="Core habits"),
        ST("Markdown routine (fresh)", "Check dates at the agreed times (e.g. 2pm and 7pm)", "Reduce by the agreed % with the right label",
           "Place marked-down items where customers see them", "Record the markdown in the system"),
        DD(["Rotate stock every time you fill", "Keep cold-chain items out of the fridge for minutes, not hours", "Report damaged deliveries at receiving"],
           ["Hide near-expiry stock at the back", "Throw away without recording", "Over-fill displays so products get crushed"]),
        K(("Target shrink (example)", "0.8%", "fresh food"), ("Markdown recovery", "60%", "of value at risk"), ("Write-offs recorded", "100%", "same day")),
    ]}],
    [MCQ("Which of these is unknown shrink?", ["Expired yoghurt written off", "A broken jar recorded as damage", "Stock missing at count with no record", "A markdown"], 2,
         "Unknown shrink is only discovered at stock count: theft, receiving and admin errors."),
     CALC("A section sold Rs 12,000,000 and recorded Rs 180,000 shrink. What is its shrink %?", "1.5%", "180,000 ÷ 12,000,000 × 100 = 1.5%."),
     TF("FEFO means the product with the earliest expiry date sells first.", True, "First expired, first out."),
     MCQ("What should you fix first?", ["The items with the highest loss value", "The items with the most units lost", "Whatever the manager noticed today", "Everything at once"], 0,
         "Value matters: a few high-value items usually cause most of the loss."),
     SC("At 8pm you find 30 cream cakes expiring tomorrow. What do you do?",
        "Mark them down by the agreed % now, display them visibly, record the markdown, and reduce tomorrow's bake.",
        "Act before it becomes waste, record it, and fix the cause (over-production).")],
    "Pick your section's top 10 loss items from last week's report. For each, write the main cause and one action, and agree them with your manager.")

# ------------------------------------------------------------------------------------------------ stock
topic("stock", "Stock management, availability and stock days", [1, 2, 3, 4, 6], ["Inventory & stock control", "Receiving & logistics"],
      "Keeping the right stock: availability, out-of-stocks, stock days and ordering.", [
    {"title": "Availability and out-of-stocks", "minutes": 20, "objectives": ["Explain OOS % and its cost", "Spot the common causes of empty shelves"],
     "blocks": [
        P("A customer who cannot find an item may buy something else, go to another store, or not come back. Availability is the first "
          "promise we make."),
        F("Out-of-stock %", "Items with zero sellable stock ÷ Items listed × 100", ["Count at a fixed time, e.g. 10am"], "60 of 1,200 items empty = 5%"),
        B("Not ordered or ordered too late", "Stock in the backroom, not on the shelf (phantom OOS)", "System stock wrong (needs a count)",
          "Supplier did not deliver", "Display too small for the sales rate", title="Common causes"),
        CH("line", "Example: OOS % by hour on a Saturday", ["9am", "11am", "1pm", "3pm", "5pm", "7pm", "9pm"], [("OOS %", [2.1, 2.8, 4.5, 6.2, 5.0, 7.4, 8.9])], "%"),
        C("warn", "Most empty shelves appear in the afternoon and evening: plan refills before the peaks, not after."),
    ]},
    {"title": "Stock days and stock accuracy", "minutes": 25, "objectives": ["Calculate stock days", "Know why too much stock is as bad as too little"],
     "blocks": [
        F("Stock days", "Average stock at cost ÷ Daily cost of goods sold", ["Daily COGS = cost of goods sold in the period ÷ days"],
          "Stock Rs 9 M, COGS Rs 300,000 a day → 30 stock days"),
        EX("Reading stock days", "Budget 25 days, actual 40 days in Light Household.",
           "That is 15 extra days: about Rs 4.5 M of cash tied up in stock that is not selling, more risk of damage and markdowns."),
        B("Too high: cash tied up, older stock, more damage and markdowns", "Too low: empty shelves and lost sales", title="Balance"),
        ST("Keep system stock accurate", "Count high-risk items weekly (cycle counts)", "Investigate every big difference before adjusting",
           "Receive correctly: count, check, then sign", "Record transfers and write-offs the same day"),
    ]}],
    [CALC("Average stock at cost is Rs 6,000,000 and COGS for 30 days is Rs 9,000,000. How many stock days?", "20 days",
          "Daily COGS = 9,000,000 ÷ 30 = 300,000. Stock days = 6,000,000 ÷ 300,000 = 20."),
     MCQ("An item shows 24 in stock but the shelf is empty. The first thing to do is:", ["Order more", "Check the backroom and count it", "Delete the item", "Ignore it"], 1,
         "This is often phantom stock: find it or correct the count before ordering."),
     TF("More stock days is always better because shelves stay full.", False, "Too much stock ties up cash and raises damage and markdown losses."),
     SC("Your section is at 42 stock days vs a 28-day budget. What do you do this week?",
        "List the slowest high-value items, stop or cut orders on them, move or promote overstock, and check for wrong system stock.",
        "Reduce inflow, speed up outflow and fix data.")],
    "Do a 10am OOS walk of your section on three days. Record each empty item and its cause, and fix the top cause.")

# ------------------------------------------------------------------------------------------------ sales KPIs
topic("sales", "Sales and the KPIs behind them", [2, 3, 4, 6], ["Sales & KPIs", "Excel / MIS"],
      "Sales vs budget, growth, basket, customers and how to read a sales report.", [
    {"title": "The sales KPIs every leader reads", "minutes": 25, "objectives": ["Calculate sales vs budget and growth", "Break sales into customers × basket"],
     "blocks": [
        F("Sales vs budget", "Actual sales ÷ Budget × 100", ["Same period for both"], "Rs 27.6 M vs Rs 30 M budget = 92%"),
        F("Growth vs last year", "(This year ÷ Last year − 1) × 100", ["Like-for-like: the same days and stores"], "Rs 33 M vs Rs 30 M = +10%"),
        F("Sales", "Customers × Average basket", ["Average basket = Sales ÷ Customers (transactions)"], "42,000 customers × Rs 2,400 = Rs 100.8 M"),
        K(("Sales vs budget", "92%", "−8 pts"), ("Growth", "+10%", "vs last year"), ("Customers", "−3%", "vs last year"), ("Basket", "+13%", "vs last year")),
        C("key", "Growth from basket with fewer customers usually means inflation, not more shoppers. Watch customer count."),
    ]},
    {"title": "Reading a sales report and acting", "minutes": 25, "objectives": ["Find the sections that explain most of a gap", "Turn findings into actions"],
     "blocks": [
        CH("hbar", "Example: gap to budget by section (Rs 000)", ["Grocery", "Beverages", "Bakery", "F&V", "Household", "Textile"],
           [("Gap to budget", [-850, -420, 160, -90, 310, -60])], "Rs 000"),
        ST("From report to action", "Find the 2–3 sections that explain most of the gap", "Check customers vs basket for each",
           "Check availability, promotions and price for the top items", "Agree actions and track them daily"),
        TB("Example action plan", ["Section", "Finding", "Action", "Owner"], [
            ["Grocery", "Top 20 items 9% OOS", "Daily 10am gap scan and reorder", "SM Grocery"],
            ["Beverages", "Competitor promotion", "Match on 10 lines, move display to entrance", "DH CG"]]),
    ]}],
    [CALC("Sales were Rs 46 M against a budget of Rs 50 M. What is sales vs budget?", "92%", "46 ÷ 50 × 100 = 92%."),
     CALC("Last year Rs 40 M, this year Rs 46 M. What is the growth?", "+15%", "(46 ÷ 40 − 1) × 100 = 15%."),
     MCQ("Sales are up 8% but customers are down 5%. What grew?", ["Customer count", "Average basket", "Stock days", "Shrink"], 1,
         "Sales = customers × basket, so the basket must have grown."),
     SC("Your store is 6% behind budget mid-month. What do you look at first?",
        "The few sections that explain most of the gap, then customers vs basket, availability of top items, promotions and price.",
        "Focus on the biggest gaps and their drivers.")],
    "Take last week's sales report. Write the three sections that explain most of the gap to budget and one action for each.")

# ------------------------------------------------------------------------------------------------ productivity
topic("productivity", "Productivity and rostering", [2, 3, 4, 6], ["Rostering & scheduling", "Team leadership"],
      "Sales per labour hour, building a rota that covers the peaks, and avoiding over- and under-staffing.", [
    {"title": "Measuring productivity", "minutes": 20, "objectives": ["Calculate sales per labour hour", "Compare productivity fairly"],
     "blocks": [
        F("Productivity", "Sales ÷ Labour hours worked", ["Labour hours from attendance / rota", "Use the same period"],
          "Rs 3,600,000 sales ÷ 1,200 hours = Rs 3,000 per hour"),
        EX("Same sales, different productivity", "Store A sells Rs 3.6 M with 1,200 hours: Rs 3,000/hour.",
           "Store B sells Rs 3.6 M with 1,500 hours: Rs 2,400/hour, 20% less productive."),
        C("tip", "Productivity rises by selling more with the same hours, or by putting hours where the customers are."),
    ]},
    {"title": "Building a rota that covers the peaks", "minutes": 30, "objectives": ["Match hours to the sales curve", "Plan offs fairly"],
     "blocks": [
        CH("bar", "Example: sales and staff by hour", ["9am", "11am", "1pm", "3pm", "5pm", "7pm", "9pm"],
           [("Sales (index)", [30, 55, 70, 65, 85, 100, 75]), ("Staff on floor (index)", [80, 90, 85, 70, 60, 55, 50])]),
        P("In the example the store is over-staffed in the morning and short in the evening peak: queues and empty shelves at 7pm."),
        ST("Rota in six steps", "Get the hourly sales curve for each day", "Set the minimum cover per hour (tills, fresh counters, floor)",
           "Place shifts so most hours overlap the peaks", "Plan weekly offs fairly and away from Friday–Sunday evenings where possible",
           "Book leave and holidays first", "Check the total hours against the budget"),
        DD(["Publish the rota at least a week ahead", "Keep a short standby list for absences"], ["Give everyone the same shift by habit", "Plan offs on peak days by default"]),
    ]}],
    [CALC("A section sold Rs 2,400,000 using 800 labour hours. What is its productivity?", "Rs 3,000 per hour", "2,400,000 ÷ 800 = 3,000."),
     MCQ("Productivity is below target but sales are on budget. The most likely cause is:", ["Too many hours", "Too few customers", "Low prices", "High shrink"], 0,
         "If sales are fine, hours are too high for those sales."),
     TF("The best rota gives every person the same shift every week.", False, "Hours should follow the sales curve; fairness comes from rotating peaks and offs."),
     SC("Queues are long at 7pm every evening but the morning is quiet. What do you change?",
        "Move hours from the morning into 5–9pm (later shifts or a mid shift), keep minimum morning cover, check total hours against budget.",
        "Match staff to the sales curve.")],
    "Draw your section's sales by hour for last Saturday and your staff on the floor by hour. Mark where you were over- and under-staffed.")

# ------------------------------------------------------------------------------------------------ customer
topic("customer", "Customer service and NPS", [1, 2, 3, 4, 6], ["Customer service"],
      "Great service on the floor, handling complaints, and what Net Promoter Score tells us.", [
    {"title": "What customers expect", "minutes": 20, "objectives": ["Name the moments that matter", "Use a greeting and help routine"],
     "blocks": [
        B("Find what I need (availability, signage, staff who know)", "Pay fast (queues, working tills)", "Fresh and clean (quality, hygiene)",
          "Be treated with respect", title="Moments that matter"),
        ST("Help routine", "See the customer and smile", "Greet: 'Assalam-o-Alaikum, can I help you find something?'",
           "Take them to the product, don't just point", "Check: 'Is there anything else?'"),
    ]},
    {"title": "Handling complaints and NPS", "minutes": 25, "objectives": ["Use the LEARN steps", "Calculate NPS"],
     "blocks": [
        ST("LEARN", "Listen without interrupting", "Empathise: 'I understand why that is frustrating'", "Apologise for the experience",
           "Resolve: fix it or offer a fair option", "Notify: record it so the cause is fixed"),
        F("Net Promoter Score", "% promoters (9–10) − % detractors (0–6)", ["Scores 7–8 are passives and not counted", "Range −100 to +100"],
          "60% promoters, 15% detractors → NPS +45"),
        CH("bar", "Example: NPS by section", ["Bakery", "Butchery", "Grocery", "F&V", "Checkout"], [("NPS", [62, 48, 35, 22, 8])]),
        C("key", "Checkout and fresh quality usually drive NPS most: fix queues and freshness first."),
    ]}],
    [CALC("Out of 200 answers, 110 gave 9–10, 50 gave 7–8 and 40 gave 0–6. What is the NPS?", "+35", "Promoters 55% − detractors 20% = 35."),
     MCQ("In LEARN, what does N stand for?", ["Negotiate", "Notify", "Never argue", "Next"], 1, "Notify: record the complaint so the cause gets fixed."),
     TF("A score of 8 out of 10 counts as a promoter.", False, "Only 9–10 are promoters; 7–8 are passives."),
     SC("A customer is angry that an advertised offer is not on the shelf. What do you do?",
        "Listen, apologise, check stock in the backroom, offer the same price on a similar item or a rain check by policy, and report the gap.",
        "LEARN, then fix the cause.")],
    "Ask 10 customers in your section 'How likely are you to recommend us, 0–10?' and why. Calculate the NPS and list the top two reasons.")

# ------------------------------------------------------------------------------------------------ leading a team
topic("leading", "Leading a team on the floor", [2, 3, 4, 6], ["Team leadership"],
      "Shift briefings, delegation, feedback and coaching for first-line leaders.", [
    {"title": "Running the shift", "minutes": 20, "objectives": ["Run a 10-minute briefing", "Delegate with clear outcomes"],
     "blocks": [
        ST("10-minute shift briefing", "Yesterday's numbers: sales, waste, OOS", "Today's priorities (max 3)", "Who does what and by when",
           "Safety or service reminder", "Thank someone for something specific"),
        B("Say what done looks like ('all milk faced and dated by 11am')", "Give the time and the standard", "Check back at the agreed time",
          title="Delegating well"),
    ]},
    {"title": "Feedback and coaching", "minutes": 25, "objectives": ["Give SBI feedback", "Coach with GROW"],
     "blocks": [
        F("SBI feedback", "Situation + Behaviour + Impact", ["Situation: when and where", "Behaviour: what they did (facts)", "Impact: what it caused"],
          "'This morning at receiving (S) you counted every crate (B), so we found a 12-crate shortage before signing (I).'"),
        ST("GROW coaching", "Goal: what do you want to achieve?", "Reality: what is happening now?", "Options: what could you do?",
           "Will: what will you do, and when?"),
        DD(["Praise in public, correct in private", "Use facts, not labels"], ["Say 'you are lazy'", "Wait for the appraisal to give feedback"]),
    ]}],
    [MCQ("In SBI, the B stands for:", ["Blame", "Behaviour", "Budget", "Briefing"], 1, "Behaviour: what the person did, described as facts."),
     TF("A good briefing has as many priorities as possible.", False, "Three priorities at most, so people remember them."),
     SC("An associate keeps arriving 15 minutes late. How do you handle it?",
        "Talk privately using SBI, listen to the reason, agree a clear expectation and a check date, follow policy if it continues.",
        "Facts, listening, clear expectation, follow-up.")],
    "Run three briefings this week using the five steps. Note what changed in your team's results.")

# ------------------------------------------------------------------------------------------------ fresh / food safety
topic("food_safety", "Fresh food standards and food safety", [1, 2, 3, 4, 6], ["Food safety", "Fresh food"],
      "Cold chain, hygiene, display and rotation for fresh counters (HACCP basics).", [
    {"title": "Cold chain and temperatures", "minutes": 20, "objectives": ["Know the key temperature limits", "Record checks correctly"],
     "blocks": [
        TB("Key temperatures (typical standards)", ["Product", "Keep at", "Action if outside"], [
            ["Chilled (dairy, deli, meat)", "0–5 °C", "Move to a working unit, record, tell your manager"],
            ["Frozen", "−18 °C or colder", "Check product, record, call maintenance"],
            ["Hot food display", "63 °C or hotter", "Reheat to 75 °C or discard by policy"]]),
        C("warn", "The danger zone is 5–63 °C: bacteria grow fast. Chilled items should be out of the fridge for minutes, not hours."),
        ST("Temperature check routine", "Check every unit at the set times", "Write the reading and sign", "Act and record if out of range"),
    ]},
    {"title": "Hygiene and display", "minutes": 20, "objectives": ["Follow personal hygiene rules", "Keep raw and ready-to-eat apart"],
     "blocks": [
        B("Wash hands before work, after breaks, after raw meat, after bins", "Hair covered, clean uniform, no jewellery at counters",
          "Separate boards and knives for raw and cooked", "Clean as you go; deep clean on schedule", title="Hygiene rules"),
        DD(["Label everything prepared in store with date and time", "Store raw meat below ready-to-eat food"], ["Top up old product on top of new", "Use the same tongs for raw and cooked"]),
    ]}],
    [MCQ("What is the safe range for chilled food?", ["0–5 °C", "8–12 °C", "−18 °C", "15–20 °C"], 0, "Chilled food is kept at 0–5 °C."),
     TF("Raw meat should be stored above ready-to-eat food.", False, "Below, so juices cannot drip onto ready-to-eat food."),
     SC("A chiller reads 9 °C at the 2pm check. What do you do?",
        "Move the products to a working chiller, record the reading and action, check how long it was warm, inform the manager and maintenance.",
        "Protect the food, record, escalate.")],
    "Shadow the temperature checks for a week. Note any reading out of range and what was done.")

# ------------------------------------------------------------------------------------------------ cash
topic("cash", "Cash handling and checkout", [1, 2, 3], ["Cash / checkout"],
      "Accurate, fast and honest till work: procedures, controls and preventing loss.", [
    {"title": "Till procedures", "minutes": 20, "objectives": ["Open and close a till correctly", "Handle refunds by policy"],
     "blocks": [
        ST("Till routine", "Count the float with a supervisor and sign", "Scan every item; check the screen price", "Count change back to the customer",
           "Refunds and voids only with supervisor approval", "Count and sign at shift end; report any difference"),
        F("Till variance", "Cash counted − Cash expected", ["Expected = float + cash sales − cash refunds"], "Counted 52,400, expected 52,900 → −500"),
        C("warn", "Never mix personal money with till money, and never leave the till open or unattended."),
    ]}],
    [CALC("Float 10,000, cash sales 46,200, cash refunds 1,200. Counted 54,700. What is the variance?", "−300",
          "Expected = 10,000 + 46,200 − 1,200 = 55,000. 54,700 − 55,000 = −300."),
     TF("A cashier can process a refund without approval if the customer has a receipt.", False, "Refunds need supervisor approval by policy."),
     SC("A customer says you gave the wrong change after they left the counter. What do you do?",
        "Stay polite, call the supervisor, check the till at the next count or CCTV by policy, and record the outcome.", "Follow the cash-dispute procedure.")],
    "Watch an experienced cashier for one shift and list three habits that keep them accurate and fast.")

# ------------------------------------------------------------------------------------------------ receiving
topic("receiving", "Receiving and backroom", [1, 2, 3], ["Receiving & logistics", "Inventory & stock control"],
      "Checking deliveries, GRN accuracy and an organised backroom.", [
    {"title": "Receiving correctly", "minutes": 20, "objectives": ["Check a delivery before signing", "Record shortages and damages"],
     "blocks": [
        ST("Receiving in six checks", "Match the delivery to the purchase order", "Count cases and units", "Check dates and temperatures (fresh, frozen)",
           "Check for damage", "Record differences on the delivery note before signing", "Post the GRN the same day"),
        EX("Why it matters", "A supplier delivers 48 cases but invoices 50. If we sign without counting, we pay for 2 cases we never got: "
           "that becomes unknown shrink at the next count."),
        DD(["Count before you sign", "Reject out-of-temperature fresh deliveries"], ["Sign blank or 'subject to count'", "Leave chilled stock on the dock"]),
    ]}],
    [MCQ("When do you record a shortage?", ["Before signing the delivery note", "At the next stock count", "When the manager asks", "Never"], 0,
         "Differences must be written on the delivery note before signing."),
     TF("Signing a delivery note 'subject to count' protects the store.", False, "Count first: suppliers rarely accept later claims.")],
    "Receive three deliveries with a senior receiver and complete the checks for each.")

# ------------------------------------------------------------------------------------------------ merchandising
topic("merch", "Merchandising and displays", [1, 2, 3, 4], ["Merchandising"],
      "Planograms, facing, promotions and displays that sell.", [
    {"title": "Displays that sell", "minutes": 20, "objectives": ["Follow a planogram", "Build a promotional display"],
     "blocks": [
        B("Eye level is buy level: best sellers and high margin at eye height", "Full, faced shelves look fresh and sell more",
          "Every product has a correct price label", "Promotions at gondola ends and entrances, with clear signs", title="Principles"),
        ST("Fill and face routine", "Bring stock to the front (facing)", "Rotate dates (FIFO/FEFO)", "Fill gaps from the backroom", "Check labels and signs"),
        CH("bar", "Example: sales uplift by display location (index)", ["Normal shelf", "Eye level", "Gondola end", "Entrance"], [("Sales index", [100, 135, 180, 220])]),
    ]}],
    [TF("The best-selling items should go on the bottom shelf so they are easy to restock.", False, "Eye level is buy level."),
     MCQ("Which location usually gives the biggest promotional uplift?", ["Bottom shelf", "Back of the store", "Entrance / gondola end", "Backroom"], 2,
         "High-traffic, visible locations sell most.")],
    "Pick one gondola end and rebuild it with a planned promotion. Compare its sales the week before and after.")

# ------------------------------------------------------------------------------------------------ store P&L
topic("pnl", "Store P&L basics", [3, 4, 6], ["Sales & KPIs", "Shrink & loss prevention"],
      "How sales become profit: margin, shrink, staff cost and the levers a manager controls.", [
    {"title": "From sales to profit", "minutes": 30, "objectives": ["Read a simple store P&L", "Know which lines a store team controls"],
     "blocks": [
        TB("Example monthly P&L (Rs M)", ["Line", "Amount", "% of sales"], [
            ["Net sales", "100.0", "100%"], ["Gross margin", "20.0", "20.0%"], ["Shrink and waste", "−1.5", "−1.5%"],
            ["Staff cost", "−7.0", "−7.0%"], ["Rent and utilities", "−6.0", "−6.0%"], ["Other costs", "−2.5", "−2.5%"], ["Store contribution", "3.0", "3.0%"]]),
        F("Gross margin %", "(Sales − Cost of goods) ÷ Sales × 100", ["Before shrink and store costs"], "Sales 100, cost 80 → 20%"),
        CH("bar", "Example: what moves contribution by Rs 1 M", ["+1% sales", "−0.2 pt shrink", "−1% staff hours", "+0.5 pt margin"], [("Rs 000", [200, 200, 70, 500])]),
        C("key", "A store team controls sales, shrink, staff hours and part of margin (mix, markdowns). That is where to focus."),
    ]}],
    [CALC("Sales Rs 80 M, cost of goods Rs 64 M. What is the gross margin %?", "20%", "(80 − 64) ÷ 80 × 100 = 20%."),
     MCQ("Which line does the store team control most directly?", ["Rent", "Shrink", "Head office cost", "Depreciation"], 1, "Shrink is driven by store habits."),
     SC("Contribution is 1 point below plan. Where do you look?", "Sales gap, shrink vs budget, staff hours vs budget and markdowns, then act on the biggest.", "Controllable lines first.")],
    "With your manager, read last month's P&L for your area. Write the two lines furthest from plan and one action for each.")

# ------------------------------------------------------------------------------------------------ performance management
topic("performance", "Managing performance", [3, 4, 6], ["Team leadership"],
      "Setting goals, regular check-ins, fair ratings and improvement plans.", [
    {"title": "Goals, check-ins and ratings", "minutes": 25, "objectives": ["Write SMART goals", "Run a monthly check-in"],
     "blocks": [
        F("SMART goal", "Specific + Measurable + Achievable + Relevant + Time-bound", [],
          "'Cut bakery waste from 2.4% to 1.6% of sales by 31 December by matching bake plans to sales by hour.'"),
        ST("Monthly check-in (20 minutes)", "Results vs goals, with numbers", "What went well", "What got in the way", "Support needed", "Next month's focus"),
        B("Rate on results and behaviours against goals, not on likeability", "Use evidence collected through the year", "Calibrate with other managers",
          title="Fair ratings"),
    ]},
    {"title": "When performance is below standard", "minutes": 20, "objectives": ["Use an improvement plan", "Keep it fair and documented"],
     "blocks": [
        ST("Performance improvement plan", "State the gap with facts", "Agree 2–3 measurable targets", "Agree support and training",
           "Set check dates (e.g. every 2 weeks)", "Record the outcome"),
        C("tip", "Most performance gaps are about clarity, skills or resources. Check these before assuming attitude."),
    ]}],
    [MCQ("Which goal is SMART?", ["Do better on waste", "Reduce waste a lot soon", "Cut bakery waste from 2.4% to 1.6% by 31 Dec", "Be more careful"], 2, "Specific, measurable and time-bound."),
     TF("Ratings should be based on evidence collected through the year.", True, "Not on the last few weeks or on likeability.")],
    "Write SMART goals for each member of your team for next quarter and agree them in a one-to-one.")

# ------------------------------------------------------------------------------------------------ health & safety
topic("safety", "Health and safety in the store", [1, 2, 3, 4, 6], ["Food safety"],
      "Preventing accidents: slips, manual handling, equipment and emergencies.", [
    {"title": "Everyday safety", "minutes": 20, "objectives": ["Spot and fix common hazards", "Lift safely"],
     "blocks": [
        B("Wet floors: clean and sign immediately", "Blocked fire exits and extinguishers: clear them now", "Overloaded high shelves: re-stack",
          "Damaged pallets and trolleys: remove from use", title="Common hazards"),
        ST("Safe lifting", "Check the weight and get help if heavy", "Feet apart, bend the knees, keep the back straight", "Hold close to the body",
           "Turn with your feet, not your back"),
        C("warn", "Every accident and near miss is reported the same day: near misses tell us where the next accident will be."),
    ]}],
    [TF("A near miss does not need to be reported because nobody was hurt.", False, "Near misses are reported to prevent the next accident."),
     MCQ("You see a fire exit blocked by cartons. You:", ["Leave it for the night team", "Clear it now and tell your supervisor", "Report it next week", "Put a sign on it"], 1,
         "Fire exits must always be clear.")],
    "Do a safety walk of your section with the checklist and fix or report every hazard.")

ROLE_TOPICS: dict[int, list[str]] = {
    1: ["customer", "food_safety", "shrink", "stock", "merch", "cash", "receiving", "safety"],
    2: ["leading", "shrink", "stock", "productivity", "customer", "food_safety", "sales", "safety"],
    3: ["sales", "shrink", "stock", "productivity", "leading", "performance", "pnl", "customer", "food_safety"],
    4: ["pnl", "sales", "performance", "productivity", "shrink", "stock", "leading", "customer"],
    6: ["pnl", "sales", "performance", "productivity", "customer", "shrink", "leading", "safety"],
}
KPI_TOPIC = {"sales": "sales", "productivity": "productivity", "shrink": "shrink", "stock_days": "stock", "rating": "performance",
             "retention": "leading", "absence": "leading", "nps": "customer", "oos": "stock"}
