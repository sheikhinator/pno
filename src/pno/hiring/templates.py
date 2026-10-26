"""Ready-made retail roles: job description, scoring rubric, interview questions and candidate messages.

Every template can be edited per vacancy; the AI (when set up) can write a fuller JD, but these work offline.
"""

from __future__ import annotations

from typing import Any

CATEGORIES: dict[str, list[str]] = {
    "Fresh food": ["Fresh food", "Butchery", "Bakery", "Deli", "Fruits & vegetables", "Food safety", "Shrink & loss prevention"],
    "FMCG / grocery": ["FMCG / grocery", "Merchandising", "Inventory & stock control", "Shrink & loss prevention"],
    "Non food": ["Non food", "Electronics", "Textile / apparel", "Merchandising", "Inventory & stock control"],
    "Cash & customer service": ["Cash / checkout", "Customer service"],
    "Receiving & stock": ["Receiving & logistics", "Inventory & stock control", "SAP / ERP"],
    "Whole store": ["Sales & KPIs", "Team leadership", "Rostering & scheduling", "Shrink & loss prevention", "Customer service", "Food safety"],
}

ROLES: dict[str, dict[str, Any]] = {
    "associate": {"title": "Sales Associate", "level": 1, "years": 0.5, "retail": 0, "education": 2, "team": 0,
                  "skills": ["Customer service", "Merchandising", "Inventory & stock control"],
                  "duties": ["Keep shelves full, faced and priced; rotate stock first-in first-out", "Help customers find products and answer questions",
                             "Record waste and damages correctly", "Support stock counts and receiving when asked", "Follow food safety and hygiene rules"],
                  "competencies": ["Customer focus", "Reliability", "Teamwork", "Attention to detail"]},
    "cashier": {"title": "Cashier", "level": 1, "years": 0.5, "retail": 0, "education": 3, "team": 0,
                "skills": ["Cash / checkout", "Customer service"],
                "duties": ["Process sales accurately and quickly at the till", "Handle cash, cards and refunds by procedure", "Balance the till at shift end",
                           "Greet customers and resolve simple complaints", "Promote loyalty programme and offers"],
                "competencies": ["Accuracy", "Integrity", "Customer focus", "Composure under pressure"]},
    "team_leader": {"title": "Team Leader", "level": 2, "years": 2, "retail": 1, "education": 3, "team": 5,
                    "skills": ["Team leadership", "Rostering & scheduling", "Inventory & stock control", "Shrink & loss prevention", "Customer service"],
                    "duties": ["Lead a team of associates on the shift: tasks, breaks, standards", "Make the rota and cover absences",
                               "Hit section availability, shrink and productivity targets", "Train new joiners on the floor",
                               "Report daily on sales, waste and out-of-stocks"],
                    "competencies": ["Leading a shift", "Planning & organising", "Coaching", "Ownership of results", "Customer focus"]},
    "section_manager": {"title": "Section Manager", "level": 3, "years": 4, "retail": 2, "education": 4, "team": 10,
                        "skills": ["Team leadership", "Sales & KPIs", "Shrink & loss prevention", "Inventory & stock control", "Rostering & scheduling", "Merchandising"],
                        "duties": ["Own the section's sales, margin, shrink and stock days against budget", "Lead team leaders and associates; rota and productivity",
                                   "Order and replenish to keep availability high and stock days on target", "Run counts, control waste and loss",
                                   "Coach the team and plan their development", "Keep food safety / display standards audit-ready"],
                        "competencies": ["Commercial acumen", "People leadership", "Planning & execution", "Problem solving", "Customer focus"]},
    "department_head": {"title": "Department Head", "level": 4, "years": 7, "retail": 4, "education": 4, "team": 30,
                        "skills": ["Team leadership", "Sales & KPIs", "Shrink & loss prevention", "Rostering & scheduling", "Excel / MIS", "Merchandising"],
                        "duties": ["Deliver the department P&L: sales, margin, shrink, productivity", "Lead section managers; build bench strength",
                                   "Plan promotions, seasons (Ramadan, Eid, 11.11) and space", "Analyse KPIs and act on gaps weekly",
                                   "Partner with buying, supply chain and P&O"],
                        "competencies": ["Strategic & commercial thinking", "Leading leaders", "Analysis & decision making", "Influence", "Driving change"]},
    "store_manager": {"title": "Store Manager", "level": 6, "years": 10, "retail": 6, "education": 4, "team": 100,
                      "skills": ["Team leadership", "Sales & KPIs", "Shrink & loss prevention", "Customer service", "Food safety", "Rostering & scheduling", "Excel / MIS"],
                      "duties": ["Run the store: sales, profit, shrink, people cost and customer NPS", "Lead department heads and the whole store team",
                                 "Build a safe, compliant, customer-first store culture", "Develop successors and manage talent",
                                 "Represent the store with the region, mall and authorities"],
                      "competencies": ["Business leadership", "People & culture", "Operational excellence", "Customer obsession", "Resilience"]},
}

QUESTIONS: dict[str, list[str]] = {
    "Customer focus": ["Tell me about a customer who was angry. What exactly did you do and what happened?"],
    "Reliability": ["How do you make sure you are on time for every shift, including weekends and Eid?"],
    "Teamwork": ["Describe a time a colleague needed help during a rush. What did you do?"],
    "Attention to detail": ["How do you check price labels and expiry dates when filling a shelf?"],
    "Accuracy": ["Your till is short by Rs 1,500 at the end of the shift. What do you do?"],
    "Integrity": ["A friend asks you to scan an item at a lower price. How do you handle it?"],
    "Composure under pressure": ["The queue is ten customers long and your printer stops. Talk me through the next five minutes."],
    "Leading a shift": ["Two people call in sick at 8am on a Friday. How do you cover the section?"],
    "Planning & organising": ["Walk me through how you build a weekly rota for your team."],
    "Coaching": ["Tell me about someone you trained who improved. What did you do differently for them?"],
    "Ownership of results": ["Your section's waste doubled last week. How do you find out why and fix it?"],
    "Commercial acumen": ["Your section is 8% below budget mid-month. What do you look at first, and what actions do you take?",
                          "How do you calculate shrink % and stock days, and what levers move each?"],
    "People leadership": ["Tell me about the weakest performer you managed. What did you do and what was the outcome?"],
    "Planning & execution": ["How did you prepare your section for Ramadan or a big promotion? What went well and what didn't?"],
    "Problem solving": ["Availability is low on your top 20 items. Walk me through your diagnosis."],
    "Strategic & commercial thinking": ["Which three KPIs tell you most about a department's health, and why?"],
    "Leading leaders": ["How do you know if a section manager is ready for promotion? Give an example."],
    "Analysis & decision making": ["Show me how you would read a weekly sales vs budget report to decide on actions."],
    "Influence": ["Tell me about a time you got buying or supply chain to change something for your department."],
    "Driving change": ["Describe a change you led that people resisted. How did you bring them along?"],
    "Business leadership": ["What would your first 90 days in this store look like?", "How do you balance sales, shrink and people cost?"],
    "People & culture": ["Turnover in the store is 40% a year. What do you do in your first month?"],
    "Operational excellence": ["How do you run a store walk, and what do you look for?"],
    "Customer obsession": ["NPS has fallen for three months. How do you find the cause and fix it?"],
    "Resilience": ["Tell me about your hardest period at work and how you handled it."],
}
SKILL_PROBES = {
    "Shrink & loss prevention": "The CV doesn't show shrink control: how would you cut waste and loss in this section?",
    "Rostering & scheduling": "How would you build a rota that covers peak hours without overtime?",
    "Team leadership": "Tell us about any time you led or guided others, even informally.",
    "Sales & KPIs": "Which numbers would you check every morning, and what would you do if one was off?",
    "Inventory & stock control": "How do you keep stock accurate between counts?",
    "Food safety": "What are the key food safety checks on a fresh counter?",
    "Customer service": "What does great service look like on a busy Saturday?",
    "Merchandising": "How do you decide what goes on the gondola end?",
    "Excel / MIS": "Which reports have you built or used, and what did you decide from them?",
    "Cash / checkout": "What are the key controls in a cash office?",
}

MESSAGES = {
    "invite": {"en": "Dear {name},\n\nThank you for applying for the {role} role at {company}. We would like to invite you for an interview on "
                     "{date} at {place}. Please bring your original educational documents and CNIC.\n\nPlease reply to confirm.\n\nRegards,\n"
                     "People & Organisation, {company}",
               "ur": "محترم {name}،\n\n{company} میں {role} کی آسامی کے لیے درخواست دینے کا شکریہ۔ ہم آپ کو {date} کو {place} میں انٹرویو کے لیے "
                     "مدعو کرتے ہیں۔ براہ کرم اپنی اصل تعلیمی اسناد اور شناختی کارڈ ساتھ لائیں۔\n\nبراہ کرم تصدیق کریں۔\n\nشکریہ،\nپیپل اینڈ آرگنائزیشن، {company}"},
    "regret": {"en": "Dear {name},\n\nThank you for your interest in the {role} role at {company} and for the time you gave us. After careful "
                     "review we will not be moving forward with your application for this role. We will keep your CV on file and contact you "
                     "if a suitable role opens.\n\nWe wish you every success.\n\nRegards,\nPeople & Organisation, {company}",
               "ur": "محترم {name}،\n\n{company} میں {role} کی آسامی میں دلچسپی اور وقت دینے کا شکریہ۔ غور کے بعد ہم اس آسامی کے لیے آپ کی درخواست "
                     "پر مزید کارروائی نہیں کر رہے۔ ہم آپ کا سی وی محفوظ رکھیں گے اور مناسب آسامی پر رابطہ کریں گے۔\n\nنیک خواہشات کے ساتھ،\nپیپل اینڈ آرگنائزیشن، {company}"},
    "offer": {"en": "Dear {name},\n\nWe are pleased to offer you the position of {role} at {company}, {store}. Your expected joining date is "
                    "{date}. The offer letter with full terms will follow. Please confirm your acceptance by replying to this message.\n\n"
                    "Welcome to the team!\n\nPeople & Organisation, {company}",
              "ur": "محترم {name}،\n\nہمیں خوشی ہے کہ ہم آپ کو {company}، {store} میں {role} کی آسامی کی پیشکش کر رہے ہیں۔ متوقع تاریخِ شمولیت {date} ہے۔ "
                    "مکمل شرائط کے ساتھ آفر لیٹر بھیجا جائے گا۔ براہ کرم جواب دے کر قبولیت کی تصدیق کریں۔\n\nٹیم میں خوش آمدید!\n\nپیپل اینڈ آرگنائزیشن، {company}"},
}
ONBOARDING = ["Offer letter signed", "CNIC copy received", "Educational documents verified", "Previous employer reference checked",
              "Medical fitness certificate", "Bank account details received", "Uniform and ID card issued", "Added to roster and biometric",
              "Day-1 induction done", "Food safety / safety training booked", "Buddy assigned for the first month"]
STAGES = [("applied", "Applied"), ("screened", "Screened"), ("interview1", "Interview 1"), ("interview2", "Interview 2"),
          ("offer", "Offer"), ("joined", "Joined"), ("rejected", "Not selected"), ("withdrawn", "Withdrew")]


def role_key(title: str) -> str:
    t = (title or "").lower()
    for key, words in (("store_manager", ["store manager", "general manager"]), ("department_head", ["department head", "dept head", "head of"]),
                       ("section_manager", ["section manager", "section head"]), ("team_leader", ["team leader", "supervisor", "team lead"]),
                       ("cashier", ["cashier", "checkout"])):
        if any(w in t for w in words):
            return key
    return "associate"


def default_rubric(role: str, category: str = "") -> dict[str, Any]:
    r = ROLES.get(role) or ROLES["associate"]
    skills = list(dict.fromkeys((CATEGORIES.get(category) or []) + r["skills"]))[:8]
    crit = [
        {"key": "years_total", "label": "Total work experience", "type": "years_total", "target": r["years"], "weight": 15},
        {"key": "years_retail", "label": "Retail / supermarket experience", "type": "years_retail", "target": r["retail"] or 0.5, "weight": 20},
        {"key": "level", "label": "Has worked at this level", "type": "level", "target": r["level"], "weight": 20},
        {"key": "skills", "label": "Skills for the role", "type": "skills", "items": skills, "weight": 25},
        {"key": "education", "label": "Education", "type": "education", "target": r["education"], "weight": 10},
        {"key": "team", "label": "Has led a team", "type": "team", "target": r["team"], "weight": 10 if r["team"] else 0},
        {"key": "city", "label": "Lives in the store's city", "type": "city", "items": [], "weight": 0},
    ]
    return {"criteria": crit, "knockouts": {"min_years": 0, "cities": [], "must_skills": []}}


def jd_text(title: str, role: str, store: str = "", section: str = "", category: str = "") -> str:
    r = ROLES.get(role) or ROLES["associate"]
    where = " · ".join(x for x in (store, section) if x)
    rub = default_rubric(role, category)
    skills = next(c["items"] for c in rub["criteria"] if c["type"] == "skills")
    lines = [f"# {title or r['title']}", f"Majid Al Futtaim · Carrefour Pakistan{(' · ' + where) if where else ''}", "",
             "## Purpose of the role",
             f"Deliver great customer experience and strong results{(' in ' + section) if section else ''} as part of the store team, "
             "living MAF values every day.", "", "## Key responsibilities"]
    lines += [f"- {d}" for d in r["duties"]]
    lines += ["", "## What you bring",
              f"- {r['years']}+ years of work experience" + (f", including {r['retail']}+ years in retail / supermarkets" if r["retail"] else ""),
              f"- Education: {['', '', 'Matric', 'Intermediate', 'Bachelor’s degree', 'Master’s degree'][r['education']]} or equivalent"]
    lines += [f"- {s}" for s in skills]
    if r["team"]:
        lines.append(f"- Experience leading a team of {r['team']}+ people")
    lines += ["- Willing to work shifts, weekends and public holidays", "", "## Competencies"] + [f"- {c}" for c in r["competencies"]]
    return "\n".join(lines)
