# workers/processor.py — replace the existing correlation block

from core.correlation import detect_and_store_correlations, detect_downstream_correlations

# ... inside the is_first block, after persist_timeline_to_redis ...

# Upstream: is this incident caused by an already-open root?
upstream_count = await detect_and_store_correlations(
    incident_id=work_item_id,
    component_type=work_item.component_type.value,
    component_id=work_item.component_id,
)

# Downstream: does this new incident explain already-open dependents?
downstream_count = await detect_downstream_correlations(
    incident_id=work_item_id,
    component_type=work_item.component_type.value,
)

correlation_count = upstream_count + downstream_count
timeline.add_event(
    "correlation_detection_completed",
    correlations_found=correlation_count,
)