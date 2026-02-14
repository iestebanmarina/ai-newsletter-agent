from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class Category(str, Enum):
    OPINION = "opinion"
    FORUM = "forum"
    REPORT = "report"
    FUTURE = "future"
    SUCCESS_CASE = "success_case"
    UNCATEGORIZED = "uncategorized"


CATEGORY_DISPLAY = {
    Category.OPINION: "Opinions & Analysis",
    Category.FORUM: "Community Discussions",
    Category.REPORT: "Research & Reports",
    Category.FUTURE: "Future Outlook",
    Category.SUCCESS_CASE: "Success Stories",
    Category.UNCATEGORIZED: "Other Notable",
}


class Article(BaseModel):
    url: str
    title: str
    source: str
    raw_content: str = ""
    summary: str = ""
    category: Category = Category.UNCATEGORIZED
    relevance_score: float = 0.0
    collected_at: datetime = Field(default_factory=datetime.utcnow)
    curated: bool = False
    sent: bool = False

    class Config:
        use_enum_values = True


class NewsletterSection(BaseModel):
    category: Category
    display_name: str
    articles: list[Article]


class Newsletter(BaseModel):
    date: datetime = Field(default_factory=datetime.utcnow)
    subject_line: str = ""
    html_content: str = ""
    json_data: str = ""
