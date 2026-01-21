"""Review manager for book review operations."""

from datetime import date, datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select, func, and_, or_, case

from ..db.models import Book
from ..db.sqlite import Database, get_db
from .models import Review
from .schemas import (
    ReviewCreate,
    ReviewUpdate,
    ReviewSummary,
    BookRatingStats,
    RatingDistribution,
    TopRatedBook,
)


class ReviewManager:
    """Manages book review operations."""

    def __init__(self, db: Optional[Database] = None):
        """Initialize review manager.

        Args:
            db: Database instance
        """
        self.db = db or get_db()

    # -------------------------------------------------------------------------
    # Review CRUD
    # -------------------------------------------------------------------------

    def create_review(self, data: ReviewCreate) -> Review:
        """Create a new review.

        Args:
            data: Review creation data

        Returns:
            Created review
        """
        with self.db.get_session() as session:
            # Verify book exists
            book = session.execute(
                select(Book).where(Book.id == str(data.book_id))
            ).scalar_one_or_none()
            if not book:
                raise ValueError("Book not found")

            # Check if review already exists for this book
            existing = session.execute(
                select(Review).where(Review.book_id == str(data.book_id))
            ).scalar_one_or_none()
            if existing:
                raise ValueError("Review already exists for this book")

            # Convert tags list to comma-separated string
            tags_str = None
            if data.tags:
                tags_str = ",".join(data.tags)

            review = Review(
                book_id=str(data.book_id),
                rating=data.rating,
                title=data.title,
                content=data.content,
                review_date=data.review_date.isoformat() if data.review_date else None,
                started_date=data.started_date.isoformat() if data.started_date else None,
                finished_date=data.finished_date.isoformat() if data.finished_date else None,
                plot_rating=data.plot_rating,
                characters_rating=data.characters_rating,
                writing_rating=data.writing_rating,
                pacing_rating=data.pacing_rating,
                enjoyment_rating=data.enjoyment_rating,
                contains_spoilers=data.contains_spoilers,
                is_favorite=data.is_favorite,
                would_recommend=data.would_recommend,
                would_reread=data.would_reread,
                tags=tags_str,
                private_notes=data.private_notes,
            )

            session.add(review)
            session.commit()
            session.refresh(review)
            session.expunge(review)

            return review

    def get_review(self, review_id: str) -> Optional[Review]:
        """Get a review by ID.

        Args:
            review_id: Review ID

        Returns:
            Review or None
        """
        with self.db.get_session() as session:
            stmt = select(Review).where(Review.id == review_id)
            review = session.execute(stmt).scalar_one_or_none()
            if review:
                session.expunge(review)
            return review

    def get_review_by_book(self, book_id: str) -> Optional[Review]:
        """Get a review by book ID.

        Args:
            book_id: Book ID

        Returns:
            Review or None
        """
        with self.db.get_session() as session:
            stmt = select(Review).where(Review.book_id == book_id)
            review = session.execute(stmt).scalar_one_or_none()
            if review:
                session.expunge(review)
            return review

    def list_reviews(
        self,
        min_rating: Optional[float] = None,
        max_rating: Optional[float] = None,
        favorites_only: bool = False,
        has_content: bool = False,
        with_spoilers: Optional[bool] = None,
        tag: Optional[str] = None,
        order_by: str = "review_date",
        descending: bool = True,
    ) -> list[Review]:
        """List reviews with optional filters.

        Args:
            min_rating: Minimum rating filter
            max_rating: Maximum rating filter
            favorites_only: Only return favorites
            has_content: Only return reviews with content
            with_spoilers: Filter by spoiler flag
            tag: Filter by tag
            order_by: Field to order by (review_date, rating, created_at)
            descending: Sort descending

        Returns:
            List of reviews
        """
        with self.db.get_session() as session:
            stmt = select(Review)

            if min_rating is not None:
                stmt = stmt.where(Review.rating >= min_rating)
            if max_rating is not None:
                stmt = stmt.where(Review.rating <= max_rating)
            if favorites_only:
                stmt = stmt.where(Review.is_favorite == True)  # noqa: E712
            if has_content:
                stmt = stmt.where(Review.content.isnot(None), Review.content != "")
            if with_spoilers is not None:
                stmt = stmt.where(Review.contains_spoilers == with_spoilers)
            if tag:
                # Search for exact tag match in comma-separated list
                # Match: "tag", ",tag,", ",tag" or "tag,"
                tag_lower = tag.lower()
                stmt = stmt.where(
                    or_(
                        func.lower(Review.tags) == tag_lower,  # Exact match (single tag)
                        func.lower(Review.tags).like(f"{tag_lower},%"),  # Starts with tag
                        func.lower(Review.tags).like(f"%,{tag_lower}"),  # Ends with tag
                        func.lower(Review.tags).like(f"%,{tag_lower},%"),  # Tag in middle
                    )
                )

            # Apply ordering
            order_column = {
                "review_date": Review.review_date,
                "rating": Review.rating,
                "created_at": Review.created_at,
                "updated_at": Review.updated_at,
            }.get(order_by, Review.review_date)

            if descending:
                stmt = stmt.order_by(order_column.desc().nullslast())
            else:
                stmt = stmt.order_by(order_column.asc().nullsfirst())

            reviews = session.execute(stmt).scalars().all()
            for review in reviews:
                session.expunge(review)
            return list(reviews)

    def update_review(
        self,
        review_id: str,
        data: ReviewUpdate,
    ) -> Optional[Review]:
        """Update a review.

        Args:
            review_id: Review ID
            data: Update data

        Returns:
            Updated review or None
        """
        with self.db.get_session() as session:
            stmt = select(Review).where(Review.id == review_id)
            review = session.execute(stmt).scalar_one_or_none()

            if not review:
                return None

            update_data = data.model_dump(exclude_unset=True)

            for field, value in update_data.items():
                if field == "tags" and value is not None:
                    review.tags = ",".join(value) if value else None
                elif field in ("review_date", "started_date", "finished_date") and value:
                    setattr(review, field, value.isoformat())
                elif hasattr(review, field):
                    setattr(review, field, value)

            review.updated_at = datetime.now(timezone.utc).isoformat()
            session.commit()
            session.refresh(review)
            session.expunge(review)

            return review

    def delete_review(self, review_id: str) -> bool:
        """Delete a review.

        Args:
            review_id: Review ID

        Returns:
            True if deleted
        """
        with self.db.get_session() as session:
            stmt = select(Review).where(Review.id == review_id)
            review = session.execute(stmt).scalar_one_or_none()

            if not review:
                return False

            session.delete(review)
            session.commit()
            return True

    # -------------------------------------------------------------------------
    # Quick Rating
    # -------------------------------------------------------------------------

    def quick_rate(
        self,
        book_id: str,
        rating: float,
        is_favorite: bool = False,
    ) -> Review:
        """Quick rate a book without full review.

        Args:
            book_id: Book ID
            rating: Rating (1-5)
            is_favorite: Mark as favorite

        Returns:
            Created or updated review
        """
        existing = self.get_review_by_book(book_id)

        if existing:
            # Update existing review
            return self.update_review(
                existing.id,
                ReviewUpdate(rating=rating, is_favorite=is_favorite),
            )
        else:
            # Create new review with just rating
            return self.create_review(
                ReviewCreate(
                    book_id=UUID(book_id),
                    rating=rating,
                    is_favorite=is_favorite,
                    review_date=date.today(),
                )
            )

    def toggle_favorite(self, book_id: str) -> Optional[Review]:
        """Toggle favorite status for a book.

        Args:
            book_id: Book ID

        Returns:
            Updated review or None
        """
        review = self.get_review_by_book(book_id)
        if not review:
            return None

        return self.update_review(
            review.id,
            ReviewUpdate(is_favorite=not review.is_favorite),
        )

    # -------------------------------------------------------------------------
    # Statistics and Reports
    # -------------------------------------------------------------------------

    def get_stats(self) -> BookRatingStats:
        """Get overall rating statistics.

        Returns:
            BookRatingStats with aggregated data
        """
        with self.db.get_session() as session:
            # Total reviews
            total_reviews = session.execute(
                select(func.count()).select_from(Review)
            ).scalar() or 0

            # Total with ratings
            total_rated = session.execute(
                select(func.count()).where(Review.rating.isnot(None))
            ).scalar() or 0

            # Average rating
            avg_rating = session.execute(
                select(func.avg(Review.rating)).where(Review.rating.isnot(None))
            ).scalar()

            # Rating distribution
            distribution = RatingDistribution()
            if total_rated > 0:
                # Count by rating range
                distribution.one_star = session.execute(
                    select(func.count()).where(
                        Review.rating.isnot(None),
                        Review.rating >= 0.5,
                        Review.rating < 1.5,
                    )
                ).scalar() or 0

                distribution.two_star = session.execute(
                    select(func.count()).where(
                        Review.rating >= 1.5,
                        Review.rating < 2.5,
                    )
                ).scalar() or 0

                distribution.three_star = session.execute(
                    select(func.count()).where(
                        Review.rating >= 2.5,
                        Review.rating < 3.5,
                    )
                ).scalar() or 0

                distribution.four_star = session.execute(
                    select(func.count()).where(
                        Review.rating >= 3.5,
                        Review.rating < 4.5,
                    )
                ).scalar() or 0

                distribution.five_star = session.execute(
                    select(func.count()).where(
                        Review.rating >= 4.5,
                    )
                ).scalar() or 0

            # Favorites count
            total_favorites = session.execute(
                select(func.count()).where(Review.is_favorite == True)  # noqa: E712
            ).scalar() or 0

            # Would recommend count
            would_recommend_count = session.execute(
                select(func.count()).where(Review.would_recommend == True)  # noqa: E712
            ).scalar() or 0

            # Would reread count
            would_reread_count = session.execute(
                select(func.count()).where(Review.would_reread == True)  # noqa: E712
            ).scalar() or 0

            # Detailed rating averages
            avg_plot = session.execute(
                select(func.avg(Review.plot_rating)).where(Review.plot_rating.isnot(None))
            ).scalar()

            avg_characters = session.execute(
                select(func.avg(Review.characters_rating)).where(
                    Review.characters_rating.isnot(None)
                )
            ).scalar()

            avg_writing = session.execute(
                select(func.avg(Review.writing_rating)).where(
                    Review.writing_rating.isnot(None)
                )
            ).scalar()

            avg_pacing = session.execute(
                select(func.avg(Review.pacing_rating)).where(Review.pacing_rating.isnot(None))
            ).scalar()

            avg_enjoyment = session.execute(
                select(func.avg(Review.enjoyment_rating)).where(
                    Review.enjoyment_rating.isnot(None)
                )
            ).scalar()

            return BookRatingStats(
                total_reviews=total_reviews,
                total_rated=total_rated,
                average_rating=round(avg_rating, 2) if avg_rating else None,
                distribution=distribution,
                total_favorites=total_favorites,
                would_recommend_count=would_recommend_count,
                would_reread_count=would_reread_count,
                avg_plot_rating=round(avg_plot, 2) if avg_plot else None,
                avg_characters_rating=round(avg_characters, 2) if avg_characters else None,
                avg_writing_rating=round(avg_writing, 2) if avg_writing else None,
                avg_pacing_rating=round(avg_pacing, 2) if avg_pacing else None,
                avg_enjoyment_rating=round(avg_enjoyment, 2) if avg_enjoyment else None,
            )

    def get_top_rated(self, limit: int = 10) -> list[TopRatedBook]:
        """Get top rated books.

        Args:
            limit: Maximum number of books to return

        Returns:
            List of top rated books
        """
        with self.db.get_session() as session:
            stmt = (
                select(Review)
                .where(Review.rating.isnot(None))
                .order_by(Review.rating.desc(), Review.is_favorite.desc())
                .limit(limit)
            )

            reviews = session.execute(stmt).scalars().all()
            result = []

            for review in reviews:
                # Get book info within session
                book = session.execute(
                    select(Book).where(Book.id == review.book_id)
                ).scalar_one_or_none()

                if book:
                    result.append(TopRatedBook(
                        book_id=UUID(review.book_id),
                        book_title=book.title,
                        book_author=book.author or "Unknown",
                        rating=review.rating,
                        review_title=review.title,
                        is_favorite=review.is_favorite,
                    ))

            return result

    def get_favorites(self) -> list[ReviewSummary]:
        """Get all favorite books.

        Returns:
            List of favorite reviews
        """
        reviews = self.list_reviews(favorites_only=True)
        return self._to_summaries(reviews)

    def get_recent_reviews(self, limit: int = 10) -> list[ReviewSummary]:
        """Get most recently reviewed books.

        Args:
            limit: Maximum number to return

        Returns:
            List of recent reviews
        """
        with self.db.get_session() as session:
            stmt = (
                select(Review)
                .order_by(Review.updated_at.desc())
                .limit(limit)
            )
            reviews = session.execute(stmt).scalars().all()
            for review in reviews:
                session.expunge(review)

        return self._to_summaries(list(reviews))

    def get_reviews_by_rating(self, rating: float) -> list[ReviewSummary]:
        """Get all reviews with a specific rating.

        Args:
            rating: Target rating (rounded to nearest 0.5)

        Returns:
            List of reviews with that rating
        """
        # Determine rating range (0.5 around target)
        min_rating = rating - 0.25
        max_rating = rating + 0.25

        reviews = self.list_reviews(min_rating=min_rating, max_rating=max_rating)
        return self._to_summaries(reviews)

    def search_reviews(self, query: str) -> list[ReviewSummary]:
        """Search reviews by content or title.

        Args:
            query: Search query

        Returns:
            List of matching reviews
        """
        with self.db.get_session() as session:
            query_lower = f"%{query.lower()}%"
            stmt = select(Review).where(
                or_(
                    func.lower(Review.title).like(query_lower),
                    func.lower(Review.content).like(query_lower),
                    func.lower(Review.tags).like(query_lower),
                )
            ).order_by(Review.updated_at.desc())

            reviews = session.execute(stmt).scalars().all()
            for review in reviews:
                session.expunge(review)

        return self._to_summaries(list(reviews))

    def get_reviews_with_tag(self, tag: str) -> list[ReviewSummary]:
        """Get all reviews with a specific tag.

        Args:
            tag: Tag to filter by

        Returns:
            List of reviews with that tag
        """
        reviews = self.list_reviews(tag=tag)
        return self._to_summaries(reviews)

    def get_all_tags(self) -> list[tuple[str, int]]:
        """Get all tags with their counts.

        Returns:
            List of (tag, count) tuples sorted by count
        """
        reviews = self.list_reviews()
        tag_counts: dict[str, int] = {}

        for review in reviews:
            for tag in review.tag_list:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1

        return sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)

    # -------------------------------------------------------------------------
    # Helper Methods
    # -------------------------------------------------------------------------

    def _to_summaries(self, reviews: list[Review]) -> list[ReviewSummary]:
        """Convert reviews to summaries with book info.

        Args:
            reviews: List of reviews

        Returns:
            List of review summaries
        """
        summaries = []

        for review in reviews:
            with self.db.get_session() as session:
                book = session.execute(
                    select(Book).where(Book.id == review.book_id)
                ).scalar_one_or_none()

                if book:
                    summaries.append(ReviewSummary(
                        id=UUID(review.id),
                        book_id=UUID(review.book_id),
                        book_title=book.title,
                        book_author=book.author or "Unknown",
                        rating=review.rating,
                        title=review.title,
                        is_favorite=review.is_favorite,
                        review_date=(
                            date.fromisoformat(review.review_date)
                            if review.review_date else None
                        ),
                        star_display=review.star_display,
                    ))

        return summaries
