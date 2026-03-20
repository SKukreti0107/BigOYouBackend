from ..schemas import CriterionAssessment
from typing import Dict,Any

def _merge_criterion(prev: Any, curr: CriterionAssessment) -> Dict[str, Any]:
        prev_completed = bool((prev or {}).get("completed", False)) if isinstance(prev, dict) else False
        prev_confidence = float((prev or {}).get("confidence", 0.0)) if isinstance(prev, dict) else 0.0
        prev_reason = (prev or {}).get("reason", "") if isinstance(prev, dict) else ""

        merged_completed = prev_completed or curr.completed
        merged_confidence = max(prev_confidence, curr.confidence)
        merged_reason = curr.reason if curr.reason else prev_reason

        return {
            "completed": merged_completed,
            "confidence": merged_confidence,
            "reason": merged_reason,
        }


def _is_complete(flag: Dict[str, Any]) -> bool:
        return bool(flag.get("completed")) and float(flag.get("confidence", 0.0)) >= 0.7