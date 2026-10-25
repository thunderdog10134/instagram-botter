#!/usr/bin/env python3
"""Stripe for Clip Autopilot (official SDK, MIT). Key: ~/secrets/stripe.json {"key": "rk_live_..."} (restricted key from J5).
  setup                                   -> products + prices (Starter 100, Growth 300, LaneB 450 USD), prints ids for ops/stripe
  link <clientSlug> <starter|growth|laneb> -> payment link URL (metadata client=<slug>, product=<name>)
  paid --since <ISO>                      -> completed checkout sessions with client/product/amount
  invoice <clientSlug> <email> <cents> <description> <weekId> -> sends an invoice (idempotent per client+week)
  invoices --open                         -> open invoices
Every call prints JSON and exits 0; errors are in the output. Never prints the key."""
import json, os, sys, time, calendar
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_secret, NoSecret, read_state, write_state, now_iso, log

PRODUCTS = {"starter": ("Pullshot Starter block (50,000 views)", 10000), "growth": ("Pullshot Growth block (165,000 views)", 30000),
            "laneb": ("Pullshot Lane B block (30 clips on your page)", 45000)}

def client():
    import stripe
    stripe.api_key = load_secret("stripe")["key"]
    stripe.max_network_retries = 3
    return stripe

def setup(s):
    ids = read_state("stripe.json", {})
    for k, (name, cents) in PRODUCTS.items():
        if k in ids:
            continue
        p = s.Product.create(name=name, metadata={"pullshot": k}, idempotency_key=f"prod-{k}-v1")
        pr = s.Price.create(product=p.id, unit_amount=cents, currency="usd", idempotency_key=f"price-{k}-v1")
        ids[k] = {"product": p.id, "price": pr.id}
    write_state("stripe.json", ids)
    return {"prices": {k: v["price"] for k, v in ids.items()}, "products": {k: v["product"] for k, v in ids.items()}}

def link(s, client_slug, prod):
    ids = read_state("stripe.json", {})
    if prod not in ids:
        return {"error": "run setup first"}
    pl = s.PaymentLink.create(line_items=[{"price": ids[prod]["price"], "quantity": 1}],
                              metadata={"client": client_slug, "product": prod},
                              payment_intent_data={"metadata": {"client": client_slug, "product": prod}},
                              idempotency_key=f"link-{client_slug}-{prod}-{time.strftime('%Y%m%d')}")
    return {"client": client_slug, "product": prod, "url": pl.url, "id": pl.id}

def paid(s, since):
    ts = calendar.timegm(time.strptime(since[:19], "%Y-%m-%dT%H:%M:%S")) if since else 0
    out = []
    for cs in s.checkout.Session.list(limit=100, created={"gte": ts}).auto_paging_iter():
        if cs.status == "complete" and cs.payment_status == "paid":
            md = dict(cs.metadata or {})
            if not md.get("client") and cs.payment_link:
                try:
                    md = dict(s.PaymentLink.retrieve(cs.payment_link).metadata or {})
                except Exception:
                    pass
            out.append({"sessionId": cs.id, "client": md.get("client"), "product": md.get("product"), "amount": (cs.amount_total or 0) / 100,
                        "email": (cs.customer_details or {}).get("email") if isinstance(cs.customer_details, dict) else getattr(cs.customer_details, "email", None),
                        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(cs.created))})
    return {"paid": out}

def invoice(s, client_slug, email, cents, desc, week):
    custs = read_state("stripe-customers.json", {})
    cid = custs.get(client_slug)
    if not cid:
        c = s.Customer.create(email=email, name=client_slug, metadata={"client": client_slug}, idempotency_key=f"cust-{client_slug}")
        cid = custs[client_slug] = c.id
        write_state("stripe-customers.json", custs)
    inv = s.Invoice.create(customer=cid, collection_method="send_invoice", days_until_due=7, auto_advance=True,
                           metadata={"client": client_slug, "week": week}, idempotency_key=f"inv-{client_slug}-{week}")
    s.InvoiceItem.create(customer=cid, invoice=inv.id, amount=int(cents), currency="usd", description=desc, idempotency_key=f"ii-{client_slug}-{week}")
    inv = s.Invoice.finalize_invoice(inv.id, idempotency_key=f"fin-{client_slug}-{week}")
    try:
        s.Invoice.send_invoice(inv.id, idempotency_key=f"send-{client_slug}-{week}")
    except Exception:
        pass
    return {"invoiceId": inv.id, "url": inv.hosted_invoice_url, "amount": int(cents) / 100, "client": client_slug, "week": week}

def open_invoices(s):
    return {"open": [{"id": i.id, "client": (i.metadata or {}).get("client"), "amount": i.amount_due / 100, "due": i.due_date, "url": i.hosted_invoice_url}
                     for i in s.Invoice.list(status="open", limit=100).auto_paging_iter()]}

def main():
    a = sys.argv[1:]
    if not a:
        print(json.dumps({"error": "usage"})); return
    try:
        s = client()
    except NoSecret:
        print(json.dumps({"error": "no stripe key yet (J5)"})); return
    except ImportError:
        print(json.dumps({"error": "stripe package missing"})); return
    try:
        if a[0] == "setup":
            r = setup(s)
        elif a[0] == "link":
            r = link(s, a[1], a[2])
        elif a[0] == "paid":
            r = paid(s, a[2] if len(a) > 2 else "")
        elif a[0] == "invoice":
            r = invoice(s, a[1], a[2], a[3], a[4], a[5])
        elif a[0] == "invoices":
            r = open_invoices(s)
        else:
            r = {"error": "unknown command"}
    except Exception as e:
        r = {"error": type(e).__name__ + ": " + str(e)[:200]}
    r["at"] = now_iso()
    log("stripe", {"cmd": a[0], "error": r.get("error")})
    print(json.dumps(r, indent=1))

if __name__ == "__main__":
    main()
