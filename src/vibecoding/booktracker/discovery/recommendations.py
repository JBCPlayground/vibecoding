"""Book recommendation engine.

Generates personalized reading recommendations based on reading history and preferences.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum
from typing import Optional

from sqlalchemy import select, func

from ..db.models import Book, ReadingLog
from ..db.schemas import BookStatus
from ..db.sqlite import Database, get_db


class RecommendationType(str, Enum):
    """Type of recommendation."""

    BY_AUTHOR = "by_author"  # More from favorite authors
    BY_GENRE = "by_genre"  # Based on preferred genres
    BY_SERIES = "by_series"  # Continue a series
    BY_LENGTH = "by_length"  # Similar length preferences
    HIGHLY_RATED = "highly_rated"  # Top rated unread
    QUICK_READ = "quick_read"  # Short books for quick wins
    LONG_AWAITED = "long_awaited"  # Oldest unread books
    RECENTLY_ADDED = "recently_added"  # Newly added to wishlist
    READ_NEXT = "read_next"  # Marked as read next


@dataclass
class Recommendation:
    """A book recommendation."""

    book: Book
    recommendation_type: RecommendationType
    reason: str
    score: float = 0.0  # Relevance score (0-1)
    metadata: dict = field(default_factory=dict)


class RecommendationEngine:
    """Generates personalized book recommendations."""

    def __init__(self, db: Optional[Database] = None):
        """Initialize recommendation engine.

        Args:
            db: Database instance
        """
        self.db = db or get_db()

    def get_recommendations(self, limit: int = 10) -> list[Recommendation]:
        """Get personalized recommendations.

        Args:
            limit: Maximum recommendations to return

        Returns:
            List of recommendations sorted by relevance
        """
        recommendations = []

        # Gather recommendations from different sources
        recommendations.extend(self._recommend_read_next())
        recommendations.extend(self._recommend_by_series())
        recommendations.extend(self._recommend_by_author())
        recommendations.extend(self._recommend_by_genre())
        recommendations.extend(self._recommend_highly_rated())
        recommendations.extend(self._recommend_quick_reads())
        recommendations.extend(self._recommend_long_awaited())

        # Remove duplicates (keep highest score)
        seen_ids = {}
        for rec in recommendations:
            if rec.book.id not in seen_ids or rec.score > seen_ids[rec.book.id].score:
                seen_ids[rec.book.id] = rec

        unique_recs = list(seen_ids.values())

        # Sort by score
        unique_recs.sort(key=lambda r: r.score, reverse=True)

        return unique_recs[:limit]

    def get_recommendations_by_type(
        self,
        rec_type: RecommendationType,
        limit: int = 10,
    ) -> list[Recommendation]:
        """Get recommendations of a specific type.

        Args:
            rec_type: Type of recommendation
            limit: Maximum results

        Returns:
            List of recommendations
        """
        type_methods = {
            RecommendationType.BY_AUTHOR: self._recommend_by_author,
            RecommendationType.BY_GENRE: self._recommend_by_genre,
            RecommendationType.BY_SERIES: self._recommend_by_series,
            RecommendationType.BY_LENGTH: self._recommend_by_length,
            RecommendationType.HIGHLY_RATED: self._recommend_highly_rated,
            RecommendationType.QUICK_READ: self._recommend_quick_reads,
            RecommendationType.LONG_AWAITED: self._recommend_long_awaited,
            RecommendationType.RECENTLY_ADDED: self._recommend_recently_added,
            RecommendationType.READ_NEXT: self._recommend_read_next,
        }

        method = type_methods.get(rec_type)
        if method:
            return method(limit=limit)
        return []

    def _recommend_read_next(self, limit: int = 5) -> list[Recommendation]:
        """Recommend books marked as 'read next'."""
        with self.db.get_session() as session:
            stmt = select(Book).where(
                Book.read_next == True,
                Book.status.in_([BookStatus.WISHLIST.value, BookStatus.ON_HOLD.value]),
            ).limit(limit)

            books = list(session.execute(stmt).scalars().all())

            recommendations = []
            for book in books:
                session.expunge(book)
                recommendations.append(Recommendation(
                    book=book,
                    recommendation_type=RecommendationType.READ_NEXT,
                    reason="You marked this as 'read next'",
                    score=1.0,  # Highest priority
                ))

            return recommendations

    def _recommend_by_series(self, limit: int = 5) -> list[Recommendation]:
        """Recommend next books in series you've started."""
        with self.db.get_session() as session:
            # Find series with completed books
            stmt = select(Book.series).where(
                Book.status == BookStatus.COMPLETED.value,
                Book.series.isnot(None),
                Book.series != "",
            ).distinct()

            started_series = [
                row[0] for row in session.execute(stmt).all()
            ]

            if not started_series:
                return []

            # Find unread books in those series
            recommendations = []
            for series in started_series[:10]:  # Limit series checked
                # Get the highest index we've read
                stmt = select(func.max(Book.series_index)).where(
                    Book.series == series,
                    Book.status == BookStatus.COMPLETED.value,
                )
                max_read_index = session.execute(stmt).scalar() or 0

                # Find next unread in series
                stmt = select(Book).where(
                    Book.series == series,
                    Book.status.in_([BookStatus.WISHLIST.value, BookStatus.ON_HOLD.value]),
                    Book.series_index > max_read_index,
                ).order_by(Book.series_index.asc()).limit(1)

                next_book = session.execute(stmt).scalar_one_or_none()

                if next_book:
                    session.expunge(next_book)
                    recommendations.append(Recommendation(
                        book=next_book,
                        recommendation_type=RecommendationType.BY_SERIES,
                        reason=f"Continue the {series} series",
                        score=0.9,
                        metadata={"series": series, "index": next_book.series_index},
                    ))

            return recommendations[:limit]

    def _recommend_by_author(self, limit: int = 5) -> list[Recommendation]:
        """Recommend books by favorite authors."""
        with self.db.get_session() as session:
            # Find favorite authors (most completed books, highest avg rating)
            stmt = select(Book).where(
                Book.status == BookStatus.COMPLETED.value
            )
            completed = list(session.execute(stmt).scalars().all())

            if not completed:
                return []

            # Score authors by books read and ratings
            author_scores = defaultdict(lambda: {"count": 0, "rating_sum": 0, "rated": 0})
            for book in completed:
                author_scores[book.author]["count"] += 1
                if book.rating:
                    author_scores[book.author]["rating_sum"] += book.rating
                    author_scores[book.author]["rated"] += 1

            # Calculate final scores
            for author, data in author_scores.items():
                avg_rating = data["rating_sum"] / data["rated"] if data["rated"] > 0 else 3
                data["score"] = data["count"] * 0.5 + avg_rating * 0.5

            # Get top authors
            top_authors = sorted(
                author_scores.items(),
                key=lambda x: x[1]["score"],
                reverse=True,
            )[:5]

            # Find unread books by these authors
            recommendations = []
            for author, data in top_authors:
                stmt = select(Book).where(
                    Book.author == author,
                    Book.status.in_([BookStatus.WISHLIST.value, BookStatus.ON_HOLD.value]),
                ).order_by(Book.date_added.desc()).limit(2)

                unread = list(session.execute(stmt).scalars().all())
                for book in unread:
                    session.expunge(book)
                    books_read = data["count"]
                    recommendations.append(Recommendation(
                        book=book,
                        recommendation_type=RecommendationType.BY_AUTHOR,
                        reason=f"You've enjoyed {books_read} book(s) by {author}",
                        score=0.8 * min(1.0, data["score"] / 10),
                        metadata={"author": author, "books_read": books_read},
                    ))

            return recommendations[:limit]

    def _recommend_by_genre(self, limit: int = 5) -> list[Recommendation]:
        """Recommend books in favorite genres."""
        with self.db.get_session() as session:
            # Find favorite genres from completed books
            stmt = select(Book).where(
                Book.status == BookStatus.COMPLETED.value
            )
            completed = list(session.execute(stmt).scalars().all())

            if not completed:
                return []

            # Count genres with ratings
            genre_scores = defaultdict(lambda: {"count": 0, "rating_sum": 0, "rated": 0})
            for book in completed:
                tags = book.get_tags()
                for tag in tags:
                    genre_scores[tag]["count"] += 1
                    if book.rating:
                        genre_scores[tag]["rating_sum"] += book.rating
                        genre_scores[tag]["rated"] += 1

            if not genre_scores:
                return []

            # Calculate scores
            for genre, data in genre_scores.items():
                avg_rating = data["rating_sum"] / data["rated"] if data["rated"] > 0 else 3
                data["score"] = data["count"] * 0.4 + avg_rating * 0.6

            # Get top genres
            top_genres = sorted(
                genre_scores.items(),
                key=lambda x: x[1]["score"],
                reverse=True,
            )[:5]

            # Find unread books in these genres
            recommendations = []
            seen_book_ids = set()

            for genre, data in top_genres:
                stmt = select(Book).where(
                    Book.status.in_([BookStatus.WISHLIST.value, BookStatus.ON_HOLD.value]),
                    func.lower(Book.tags).like(f'%"{genre.lower()}"%'),
                ).order_by(Book.date_added.desc()).limit(3)

                unread = list(session.execute(stmt).scalars().all())
                for book in unread:
                    if book.id not in seen_book_ids:
                        seen_book_ids.add(book.id)
                        session.expunge(book)
                        recommendations.append(Recommendation(
                            book=book,
                            recommendation_type=RecommendationType.BY_GENRE,
                            reason=f"You enjoy {genre} books",
                            score=0.7 * min(1.0, data["score"] / 10),
                            metadata={"genre": genre, "books_in_genre": data["count"]},
                        ))

            return recommendations[:limit]

    def _recommend_by_length(self, limit: int = 5) -> list[Recommendation]:
        """Recommend books similar in length to preferred reading."""
        with self.db.get_session() as session:
            # Calculate preferred page count from recent reads
            three_months_ago = (date.today() - timedelta(days=90)).isoformat()
            stmt = select(Book).where(
                Book.status == BookStatus.COMPLETED.value,
                Book.date_finished >= three_months_ago,
                Book.page_count.isnot(None),
            )
            recent_reads = list(session.execute(stmt).scalars().all())

            if len(recent_reads) < 3:
                return []

            # Calculate average page count
            avg_pages = sum(b.page_count for b in recent_reads) / len(recent_reads)
            min_pages = int(avg_pages * 0.7)
            max_pages = int(avg_pages * 1.3)

            # Find unread books in that range
            stmt = select(Book).where(
                Book.status.in_([BookStatus.WISHLIST.value, BookStatus.ON_HOLD.value]),
                Book.page_count >= min_pages,
                Book.page_count <= max_pages,
            ).order_by(Book.date_added.desc()).limit(limit)

            unread = list(session.execute(stmt).scalars().all())

            recommendations = []
            for book in unread:
                session.expunge(book)
                recommendations.append(Recommendation(
                    book=book,
                    recommendation_type=RecommendationType.BY_LENGTH,
                    reason=f"Similar length to books you typically read (~{int(avg_pages)} pages)",
                    score=0.5,
                    metadata={"avg_preferred_pages": int(avg_pages)},
                ))

            return recommendations

    def _recommend_highly_rated(self, limit: int = 5) -> list[Recommendation]:
        """Recommend unread books that are highly rated."""
        with self.db.get_session() as session:
            # Books marked with high Goodreads rating
            stmt = select(Book).where(
                Book.status.in_([BookStatus.WISHLIST.value, BookStatus.ON_HOLD.value]),
                Book.goodreads_avg_rating >= 4.0,
            ).order_by(Book.goodreads_avg_rating.desc()).limit(limit)

            highly_rated = list(session.execute(stmt).scalars().all())

            recommendations = []
            for book in highly_rated:
                session.expunge(book)
                recommendations.append(Recommendation(
                    book=book,
                    recommendation_type=RecommendationType.HIGHLY_RATED,
                    reason=f"Highly rated ({book.goodreads_avg_rating:.1f} on Goodreads)",
                    score=0.6,
                    metadata={"goodreads_rating": book.goodreads_avg_rating},
                ))

            return recommendations

    def _recommend_quick_reads(self, limit: int = 5) -> list[Recommendation]:
        """Recommend short books for quick reads."""
        with self.db.get_session() as session:
            stmt = select(Book).where(
                Book.status.in_([BookStatus.WISHLIST.value, BookStatus.ON_HOLD.value]),
                Book.page_count.isnot(None),
                Book.page_count <= 200,
                Book.page_count >= 50,
            ).order_by(Book.page_count.asc()).limit(limit)

            short_books = list(session.execute(stmt).scalars().all())

            recommendations = []
            for book in short_books:
                session.expunge(book)
                recommendations.append(Recommendation(
                    book=book,
                    recommendation_type=RecommendationType.QUICK_READ,
                    reason=f"Quick read at just {book.page_count} pages",
                    score=0.4,
                    metadata={"page_count": book.page_count},
                ))

            return recommendations

    def _recommend_long_awaited(self, limit: int = 5) -> list[Recommendation]:
        """Recommend books that have been on wishlist longest."""
        with self.db.get_session() as session:
            stmt = select(Book).where(
                Book.status.in_([BookStatus.WISHLIST.value, BookStatus.ON_HOLD.value]),
                Book.date_added.isnot(None),
            ).order_by(Book.date_added.asc()).limit(limit)

            oldest = list(session.execute(stmt).scalars().all())

            recommendations = []
            for book in oldest:
                session.expunge(book)

                # Calculate how long it's been waiting
                if book.date_added:
                    added = date.fromisoformat(book.date_added)
                    days_waiting = (date.today() - added).days
                    time_str = f"{days_waiting} days" if days_waiting < 365 else f"{days_waiting // 365} year(s)"
                else:
                    time_str = "a while"
                    days_waiting = 0

                recommendations.append(Recommendation(
                    book=book,
                    recommendation_type=RecommendationType.LONG_AWAITED,
                    reason=f"Been on your list for {time_str}",
                    score=0.3,
                    metadata={"days_waiting": days_waiting},
                ))

            return recommendations

    def _recommend_recently_added(self, limit: int = 5) -> list[Recommendation]:
        """Recommend recently added books."""
        with self.db.get_session() as session:
            stmt = select(Book).where(
                Book.status.in_([BookStatus.WISHLIST.value, BookStatus.ON_HOLD.value]),
            ).order_by(Book.date_added.desc()).limit(limit)

            recent = list(session.execute(stmt).scalars().all())

            recommendations = []
            for book in recent:
                session.expunge(book)
                recommendations.append(Recommendation(
                    book=book,
                    recommendation_type=RecommendationType.RECENTLY_ADDED,
                    reason="Recently added to your list",
                    score=0.35,
                ))

            return recommendations

    def get_what_to_read_next(self) -> Optional[Recommendation]:
        """Get single best recommendation for what to read next.

        Returns:
            Top recommendation or None
        """
        recommendations = self.get_recommendations(limit=1)
        return recommendations[0] if recommendations else None
