# Research Prompt — VisionSense Market, Pricing & Dashboard Strategy

*Copy everything below this line into your research tool / hand to your researcher.*

---

You are a market researcher and product strategist. I am the founder of **VisionSense**,
a computer-vision startup in **Pakistan**. Below is complete context on my company. Read
it carefully, then answer the research questions at the end. Ground every answer in
evidence (cite sources); where data on Pakistan is thin, use comparable markets (India,
Bangladesh, GCC, Southeast Asia) and say so explicitly. Mark each conclusion with your
confidence level (high / medium / low).

## 1. What we do

We turn a business's **existing CCTV cameras into an AI analytics and alerting system**.
We install one GPU server on the client's premises; it connects to their existing
cameras/NVR over the local network and runs object-detection AI (YOLO-class models) with
object tracking and a business-rules engine on every camera feed. No new cameras are
needed, video never leaves their building, and the system keeps working when the
internet is down. Alerts go to the owner's **WhatsApp with a photo snapshot** (e.g.,
"cash counter unmanned for 6 minutes — 2:14 pm — [photo]").

## 2. How we do it (plain English)

- One mid-range NVIDIA GPU server handles 8–32 cameras depending on the package
  (we have measured this precisely on real camera streams).
- Every application is the same pipeline: detect → track → apply a business rule →
  alert/report. Different clients get different rule configurations, not different
  software. This means we can add a new "app" to an installed site remotely in minutes.
- We can fix bugs and push updates to every client's server remotely from our office.

## 3. Who our clients are (Pakistan SME + mid-market, owner-operated)

| Segment | Example | What they buy |
|---|---|---|
| Retail marts & grocery chains | 5,000–30,000 sq-ft supermarkets | theft alerts, footfall counting, staff phone-usage detection, counter-coverage alerts, queue alerts, aisle heatmaps, face-recognition attendance |
| Distributors & warehouses (pharma/FMCG) | 20–50 staff distribution godowns | gate attendance, restricted-zone intrusion, carton counting, vehicle number-plate logging, after-hours alerts |
| Restaurants & QSR | dine-in + kitchen | hygiene compliance (hairnets/gloves), kitchen fire early-warning, table turnover, queue length, till-area monitoring |
| Small factories | textile, plastics, food processing | PPE (helmet/vest) compliance with photo evidence, danger-zone intrusion, fire/smoke detection, man-down detection, line-manning counts |
| Banks & offices | branches, BPOs | queue analytics, covered-face alerts at entrance, weapon detection on critical cameras, attendance, after-hours vault-zone alarms |
| Schools & hospitals | private institutions | attendance, perimeter intrusion, patient-fall detection, crowd density |
| Petrol pumps & fleet | fuel stations | drive-off (fuel theft) plate capture, attendant-presence per pump, no-smoking/no-phone enforcement in fuel zones |
| Gated societies | private housing schemes | gate number-plate entry, guard-patrol verification, perimeter crossing, night loitering |

The buyer is typically the **owner ("seth") or GM** — not an IT department. Their
motivations, in order: (1) theft and pilferage by staff/customers, (2) staff discipline
and attendance fraud, (3) watching the business from their phone while away,
(4) safety/compliance (factories, food), (5) customer analytics (footfall) last.

## 4. Our business model (two revenue streams)

**A. One-time on-site sale:** GPU server hardware + installation + perpetual license for
the purchased apps. Price bands: small shop (6–8 cameras) ≈ PKR 175–250k; standard site
(12–16 cameras) ≈ PKR 240–320k; large site (24–32 cameras) ≈ PKR 380–550k. The system
runs forever on their premises even if they never pay us again — we use this honesty as
a selling point against cloud-camera competitors.

**B. Monthly subscription — the cloud dashboard (this is what I need researched most):**
the on-site server pushes *events and statistics* (never video) to our cloud. The owner
gets a web/mobile dashboard: live status of all cameras and alerts, analytics
(footfall trends, queue times, heatmaps), attendance reports, compliance scorecards,
weekly PDF/WhatsApp summary reports, and — for chains — **multi-branch comparison**
(rank my 5 stores by footfall, by violations, by queue time). Also sold as subscription:
a "Care Plan" (we remotely monitor their server health, push updates, priority support),
add-on apps enabled remotely, and WhatsApp alert quotas. Working price anchor:
PKR 8,000–25,000/month per site depending on tier.

## 5. Research questions — answer all, in this order

**Market & demand**
1. Size the addressable market in Pakistan for each client segment above (counts of
   supermarkets/marts, restaurants, small factories, private schools/hospitals, petrol
   stations, gated societies). Cite sources; rough counts are fine if sourced.
2. What is the current penetration of CCTV in these segments, and what do they already
   spend on cameras/NVRs/guards? (Their existing spend is our pricing anchor.)
3. Which 2–3 segments should we prioritize first for fastest sales cycles, and why?

**Competition**
4. Map competitors: (a) local Pakistani CCTV integrators adding "AI analytics", (b) the
   built-in AI in Hikvision/Dahua NVRs (line-crossing, intrusion, face) — how good is it
   really and why would a client pay us when their NVR has "AI" checkboxes?, (c) regional
   startups (India: Staqu/JARVIS, Wobot; GCC; SEA), (d) global cloud players
   (Verkada, Rhombus, Eagle Eye, Coram) — could they enter Pakistan?
5. For each competitor class: pricing, what they do better than us, our defensible edge
   (our thesis: on-prem privacy, WhatsApp-first alerts, Urdu-market sales motion,
   rules customized per business, no camera replacemaent required — validate or challenge this).

**Subscription & dashboard (most important section)**
6. Evidence from comparable markets: will Pakistani SME owners pay a **monthly** fee for
   analytics dashboards? What monthly price points survive churn for SME SaaS in
   Pakistan/India (POS systems, khata apps, payroll apps are good analogies)?
7. **What should the dashboard show to justify the subscription every single month?**
   Rank candidate features by retention value, with evidence from analogous products:
   daily WhatsApp digest, theft/violation photo log, attendance/payroll export,
   footfall trends, queue/service times, compliance league tables across branches,
   heatmaps, monthly PDF "business health" report, anomaly callouts ("today's footfall
   40% below normal"). What do owners actually open weekly vs. never?
8. What causes SME SaaS churn in Pakistan and how do successful vendors fight it
   (annual prepay discounts, WhatsApp-based delivery instead of web login, dealer-collected
   payments, bundling with support)?
9. Payment rails: what works for recurring B2B SME collection in Pakistan (bank
   standing orders, JazzCash/Easypaisa, manual invoicing + field collection)? Real-world
   failure rates of card-based recurring billing there.

**Go-to-market & operations**
10. Channel strategy: should we sell direct, or through the existing CCTV
    dealer/installer network (they own the client relationships)? What margins do
    security-equipment dealers in Pakistan expect, and how have similar software vendors
    structured dealer programs?
11. Regulatory: rules on face recognition of employees/customers in Pakistan (PECA,
    any provincial rules), NADRA considerations, and what consent/signage practice we
    should adopt to be safe and sellable to banks/schools.
12. Case studies: 3–5 detailed examples of companies (any market) that sold
    on-prem/edge video analytics to SMEs with a subscription dashboard on top — what
    worked, what killed them, unit economics if public.

**Output format:** a structured report following the section order above; executive
summary of ≤15 bullet points at top; every factual claim sourced; each recommendation
tagged high/medium/low confidence; end with the 10 riskiest assumptions in my plan
ranked by how cheaply I can test each one.
