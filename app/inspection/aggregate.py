import json
from collections import Counter, defaultdict

def _safe_json(s, default):
    try:
        return json.loads(s) if s else default
    except Exception:
        return default

def aggregate_run(frames):
    """
    frames: list[InspectionFrame]
    Returns report_json dict.
    """
    total = len(frames)
    processed = 0
    healthy = 0
    stressed = 0

    issue_counts = Counter()
    severity_counts = Counter()
    conf_sum = defaultdict(float)
    conf_n = defaultdict(int)

    hotspots = []
    previews = []

    # pick top 20 frames for preview (worst first)
    scored = []

    for f in frames:
        findings = _safe_json(f.findings_json, {})
        meta = _safe_json(f.meta_json, {})

        if f.status == "done":
            processed += 1

        issues = findings.get("issues", []) if isinstance(findings, dict) else []
        plant_health = findings.get("plant_health", "unknown")

        if plant_health == "healthy":
            healthy += 1
        elif plant_health == "stressed":
            stressed += 1

        # score frame: more issues + higher conf = more important
        frame_score = 0.0
        for iss in issues:
            t = iss.get("type", "unknown")
            sev = iss.get("severity", "low")
            conf = float(iss.get("confidence", 0.0) or 0.0)
            issue_counts[t] += 1
            severity_counts[sev] += 1
            conf_sum[t] += conf
            conf_n[t] += 1

            w = 3 if sev == "high" else (2 if sev == "medium" else 1)
            frame_score += w * conf

            # hotspot needs pose (odom)
            odom = meta.get("odom") or {}
            x = odom.get("x")
            y = odom.get("y")
            if isinstance(x, (int, float)) and isinstance(y, (int, float)):
                hotspots.append({
                    "x": float(x),
                    "y": float(y),
                    "issue": t,
                    "severity": sev,
                    "confidence": conf,
                    "frame_id": f.id,
                })

        scored.append((frame_score, f, findings, meta))

    # compute top issues list
    top_issues = []
    for t, c in issue_counts.most_common(10):
        avg_conf = (conf_sum[t] / conf_n[t]) if conf_n[t] else 0.0
        top_issues.append({
            "type": t,
            "count": int(c),
            "avg_conf": round(avg_conf, 3),
        })

    # previews: top 20 by score
    scored.sort(key=lambda x: x[0], reverse=True)
    for score, f, findings, meta in scored[:20]:
        previews.append({
            "frame_id": f.id,
            "ts": f.ts,
            "status": f.status,
            "image_path": f.image_path,  # you may convert to URL in route
            "findings": findings,
            "meta": meta,
            "score": round(float(score), 3),
        })

    report = {
        "stats": {
            "total_frames": total,
            "processed": processed,
            "healthy_frames": healthy,
            "stressed_frames": stressed,
            "severity_distribution": dict(severity_counts),
            "top_issues": top_issues,
        },
        "hotspots": hotspots[:200],  # cap to avoid huge payload
        "frames_preview": previews,
    }
    return report
