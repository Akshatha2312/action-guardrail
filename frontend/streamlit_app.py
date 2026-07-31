"""AI Action Guardrail & Governance Platform - Streamlit Dashboard."""
import os
import time

import pandas as pd
import requests
import streamlit as st

API_URL = "https://action-guardrail-pug7.onrender.com"
st.set_page_config(page_title="AI Action Guardrail", page_icon="🛡️", layout="wide")

# ---------------------------------------------------------------- styling --
st.markdown(
    """
    <style>
    .main-header {font-size: 2.1rem; font-weight: 700; margin-bottom: 0;}
    .sub-header {color: #6b7280; margin-top: 0; margin-bottom: 1.5rem;}
    div[data-testid="stMetric"] {
    background: #1e293b !important;
    border: 1px solid #334155;
    border-left: 4px solid #3b82f6;
    border-radius: 10px;
    padding: 14px 18px;
}
div[data-testid="stMetric"] label[data-testid="stMetricLabel"],
div[data-testid="stMetric"] div[data-testid="stMetricLabel"] {
    color: #94a3b8 !important;
    font-size: 0.85rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.03em;
}
div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
    color: #f8fafc !important;
    font-size: 1.9rem;
    font-weight: 700;
}
    .badge {padding: 3px 10px; border-radius: 12px; font-size: 0.78rem; font-weight: 600;}
    .badge-block {background:#fee2e2; color:#991b1b;}
    .badge-hitl {background:#fef3c7; color:#92400e;}
    .badge-allow {background:#dcfce7; color:#166534;}
    </style>
    """,
    unsafe_allow_html=True,
)


def api_get(path, **params):
    try:
        r = requests.get(f"{API_URL}{path}", params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"API error calling GET {path}: {e}")
        return None


def api_post(path, json_body=None):
    try:
        r = requests.post(f"{API_URL}{path}", json=json_body or {}, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"API error calling POST {path}: {e}")
        return None


def outcome_badge(outcome: str) -> str:
    mapping = {
        "block": ("BLOCKED", "badge-block"),
        "require_hitl": ("HITL REQUIRED", "badge-hitl"),
        "log_and_allow": ("ALLOWED", "badge-allow"),
    }
    label, css = mapping.get(outcome, (outcome, "badge-allow"))
    return f'<span class="badge {css}">{label}</span>'


st.markdown('<p class="main-header">🛡️ AI Action Guardrail & Governance Platform</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">Policy-driven evaluation of every agent tool call, before execution.</p>', unsafe_allow_html=True)

with st.sidebar:
    st.header("Navigation")
    page = st.radio("Go to", ["Dashboard", "Run Demo Scenarios", "Test an Action", "HITL Review Queue", "Policies", "Audit Log"])
    st.divider()
    health = api_get("/health")
    if health and health.get("status") == "ok":
        st.success("API: connected")
    else:
        st.error("API: unreachable — start FastAPI on :8000")
    st.caption(f"API URL: {API_URL}")

# ---------------------------------------------------------------- Dashboard --
if page == "Dashboard":
    metrics = api_get("/metrics") or {}
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Evaluated", metrics.get("total_evaluated", 0))
    c2.metric("Allowed", metrics.get("allowed", 0))
    c3.metric("Blocked", metrics.get("blocked", 0))
    c4.metric("HITL Pending", metrics.get("hitl_pending", 0))

    st.subheader("Recent Actions")
    logs = api_get("/audit-logs", limit=25) or []
    if logs:
        df = pd.DataFrame(logs)
        for _, row in df.iterrows():
            with st.container(border=True):
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.markdown(
                        f"**{row['action_type']}** via `{row['tool_name']}`  "
                        f"&nbsp;|&nbsp; Agent: `{row['agent_id']}`  "
                        f"&nbsp;|&nbsp; {row['timestamp']}",
                    )
                    st.caption(f"Matched policy: `{row['matched_policy'] or 'default (no rule matched)'}` — {row['reason']}")
                    st.json(row["parameters"], expanded=False)
                with col2:
                    st.markdown(outcome_badge(row["outcome"]), unsafe_allow_html=True)
                    st.caption(row["execution_status"])
    else:
        st.info("No actions evaluated yet. Try 'Run Demo Scenarios' or 'Test an Action'.")

# ---------------------------------------------------------------- Demo --
elif page == "Run Demo Scenarios":
    st.subheader("Run Demo Scenarios")
    st.write(
        "Executes the 5 required demonstration scenarios through the **real** "
        "guardrail evaluation flow (no hardcoded outcomes)."
    )
    if st.button("▶ Run Demo Scenarios", type="primary"):
        with st.spinner("Running scenarios through the guardrail..."):
            results = api_post("/demo/run")
        if results:
            for r in results:
                status_icon = "✅" if r["passed"] else "❌"
                with st.container(border=True):
                    st.markdown(
                        f"{status_icon} **{r['action_type']}** — Agent `{r['agent_id']}`  "
                        f"&nbsp;→&nbsp; {outcome_badge(r['actual_outcome'])}",
                        unsafe_allow_html=True,
                    )
                    st.caption(
                        f"Expected: `{r['expected_outcome']}` · Matched policy: "
                        f"`{r['matched_policy'] or 'default'}` · Execution: `{r['execution_status']}`"
                    )
                    st.json(r["parameters"], expanded=False)
            passed = sum(1 for r in results if r["passed"])
            st.success(f"{passed}/{len(results)} scenarios matched expected outcome.")

# ---------------------------------------------------------------- Manual test --
elif page == "Test an Action":
    st.subheader("Demo Action Testing")
    st.write("Submit a custom action through the guardrail evaluation flow.")

    action_type = st.selectbox(
        "Action Type", ["database_delete", "database_read", "send_email", "file_read"]
    )
    agent_id = st.text_input("Agent ID", value="agent-manual-test")
    tool_name = st.text_input("Tool Name", value="manual_tool")

    parameters = {}
    if action_type == "database_delete":
        parameters["record_count"] = st.number_input("Record Count", min_value=0, value=10, step=1)
        parameters["table"] = st.text_input("Table", value="users")
    elif action_type == "database_read":
        parameters["table"] = st.text_input("Table", value="orders")
    elif action_type == "send_email":
        parameters["recipient"] = st.text_input("Recipient Email", value="someone@example.com")
        parameters["recipient_domain"] = st.text_input(
            "Recipient Domain (used by the policy engine)",
            value=parameters["recipient"].split("@")[-1] if "@" in parameters["recipient"] else "",
        )
        parameters["subject"] = st.text_input("Subject", value="Hello")
    elif action_type == "file_read":
        parameters["path"] = st.text_input("File Path", value="/data/reports/summary.pdf")

    if st.button("Evaluate Action", type="primary"):
        payload = {
            "agent_id": agent_id,
            "action_type": action_type,
            "tool_name": tool_name,
            "parameters": parameters,
        }
        result = api_post("/actions/evaluate", payload)
        if result:
            st.markdown(outcome_badge(result["outcome"]), unsafe_allow_html=True)
            st.write(f"**Matched policy:** `{result['matched_policy'] or 'default (no rule matched)'}`")
            st.write(f"**Reason:** {result['reason']}")
            st.write(f"**Execution status:** `{result['execution_status']}`")
            if result.get("execution_result"):
                st.json(result["execution_result"])
            if result["outcome"] == "require_hitl":
                st.warning("This action is now pending human approval — see the HITL Review Queue.")

# ---------------------------------------------------------------- HITL --
elif page == "HITL Review Queue":
    st.subheader("Human-in-the-Loop Review Queue")
    pending = api_get("/hitl/pending") or []
    if not pending:
        st.info("No actions pending approval.")
    for item in pending:
        with st.container(border=True):
            st.markdown(f"### {item['action_type']} — Agent `{item['agent_id']}`")
            colA, colB = st.columns(2)
            with colA:
                st.write(f"**Timestamp:** {item['timestamp']}")
                st.write(f"**Tool:** {item['tool_name']}")
                st.write(f"**Matched policy:** `{item['matched_policy']}`")
                st.write(f"**Risk / reason:** {item['reason']}")
            with colB:
                st.write("**Parameters:**")
                st.json(item["parameters"], expanded=False)

            reviewer = st.text_input("Reviewer name", value="reviewer1", key=f"reviewer_{item['request_id']}")
            c1, c2 = st.columns(2)
            if c1.button("✅ APPROVE", key=f"approve_{item['request_id']}", type="primary"):
                res = api_post(f"/hitl/{item['request_id']}/approve", {"decided_by": reviewer})
                if res:
                    st.success(f"Approved and executed. Status: {res['execution_status']}")
                    time.sleep(0.8)
                    st.rerun()
            if c2.button("❌ REJECT", key=f"reject_{item['request_id']}"):
                res = api_post(f"/hitl/{item['request_id']}/reject", {"decided_by": reviewer})
                if res:
                    st.warning("Rejected. Action was not executed.")
                    time.sleep(0.8)
                    st.rerun()

# ---------------------------------------------------------------- Policies --
elif page == "Policies":
    st.subheader("Active Policies")
    data = api_get("/policies")
    if data:
        st.write(f"**Internal domains** (used by `external_domain` operator): {', '.join(data['internal_domains'])}")
        for rule in data["policies"]:
            with st.container(border=True):
                st.markdown(f"**`{rule['id']}`** — {rule['description']}")
                st.caption(
                    f"action_type=`{rule['action_type']}` · "
                    f"condition: `{rule['condition']}` · outcome=`{rule['outcome']}`"
                )

# ---------------------------------------------------------------- Audit log --
elif page == "Audit Log":
    st.subheader("Full Audit Log")
    logs = api_get("/audit-logs", limit=500) or []
    if logs:
        df = pd.DataFrame(logs)[
            ["timestamp", "agent_id", "action_type", "tool_name", "matched_policy",
             "outcome", "execution_status", "human_decision", "request_id"]
        ]
        st.dataframe(df, use_container_width=True, height=500)
        st.download_button(
            "Download audit log (CSV)",
            df.to_csv(index=False).encode("utf-8"),
            file_name="audit_log.csv",
            mime="text/csv",
        )
    else:
        st.info("No audit events yet.")
