import re
import unicodedata


STOP_WORDS = {
    "anh", "ban", "biet", "cai", "cac", "cho", "co", "cua", "da", "day",
    "do", "duoc", "em", "gio", "giup", "hay", "la", "lam", "len", "luc",
    "ma", "minh", "mot", "nay", "nhe", "neu", "nguoi", "o", "roi", "se",
    "tai", "the", "thi", "toi", "trong", "va", "vay", "voi",
}
GENERIC_CLAIMS = (
    "do cua toi",
    "la cua toi",
    "dung mo ta",
    "toi mat do nay",
    "xin nhan lai",
)


def _normalize(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text.lower().replace("đ", "d"))
    return "".join(char for char in normalized if unicodedata.category(char) != "Mn")


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]{2,}", _normalize(text))
        if token not in STOP_WORDS and not token.isdigit()
    }


def is_useful_clue(text: str) -> bool:
    return len(_tokens(text)) >= 3


def analyze_claim(
    private_clue: str,
    claim: str,
    previous_rejections: int = 0,
    recent_claims: int = 0,
) -> dict:
    """Score only the private match evidence and explain indicators for human review."""
    score = 10
    reasons = []
    clue_tokens = _tokens(private_clue)
    claim_tokens = _tokens(claim)

    if len(clue_tokens) < 3:
        score = 50
        reasons.append("Tin đăng chưa có đủ đặc điểm riêng để AI đối chiếu.")
    else:
        matched = clue_tokens & claim_tokens
        coverage = len(matched) / len(clue_tokens)
        if coverage == 0:
            score += 50
            reasons.append("Câu trả lời chưa nhắc đến đặc điểm riêng đã được người nhặt lưu.")
        elif coverage < 0.25:
            score += 40
            reasons.append("Có rất ít từ khóa trùng với đặc điểm riêng của món đồ.")
        elif coverage < 0.5:
            score += 25
            reasons.append("Câu trả lời mới khớp một phần với đặc điểm riêng.")

    if len(claim_tokens) < 5:
        score += 20
        reasons.append("Thông tin xác minh khá ngắn, khó dùng để đối chiếu.")

    normalized_claim = _normalize(claim)
    if len(claim_tokens) < 10 and any(phrase in normalized_claim for phrase in GENERIC_CLAIMS):
        score += 15
        reasons.append("Câu trả lời có nội dung chung chung, chưa thể hiện chi tiết nhận dạng.")

    if previous_rejections >= 2:
        score += 15
        reasons.append("Tài khoản từng có nhiều yêu cầu xác minh bị từ chối.")
    if recent_claims >= 3:
        score += 10
        reasons.append("Tài khoản gửi nhiều yêu cầu xác minh trong thời gian ngắn.")

    score = min(score, 100)
    level = "high" if score >= 60 else "medium" if score >= 30 else "low"
    if not reasons:
        reasons.append("Một số từ khóa khớp với đặc điểm riêng; vẫn cần người nhặt kiểm tra trực tiếp.")
    return {
        "risk_score": score,
        "risk_level": level,
        "risk_reasons": reasons,
        "engine": "local-clue-match-v1",
    }
