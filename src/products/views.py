from django.contrib import messages
from django.db.models import Avg, Count
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .forms import CommentForm
from .models import Category, Comment, Product


def product_list(request, category_slug=None):
    categories = Category.objects.all()
    products = Product.objects.select_related("category").annotate(
        avg_rating=Avg("comments__rating"), total_ratings=Count("comments")
    )
    if category_slug:
        products = products.filter(category__slug=category_slug)
    return render(
        request,
        "products.html",
        {"categories": categories, "products": products},
    )


def product_detail(request, category_slug, pk):
    """
    Display a single product's detail page and handle review submissions.

    Fetches the specified product with related category, tags, and aggregated
    rating metrics. Supports POST submissions for both authenticated users
    (upserting existing reviews) and guests (creating new reviews). Also builds
    a list of top-rated related products in the same category.

    Args:
        request (HttpRequest): The Django request object.
        category_slug (str): Slug identifier of the product's category.
        pk (int): Primary key of the product.

    Returns:
        HttpResponse: Rendered product detail page, or a redirect response
        upon successful review submission.
    """
    product = get_object_or_404(
        Product.objects.select_related("category")
        .prefetch_related("tags")
        .annotate(avg_rating=Avg("comments__rating"), total_ratings=Count("comments")),
        pk=pk,
        category__slug=category_slug,
    )

    related_products = (
        Product.objects.filter(category=product.category)
        .exclude(pk=product.pk)
        .annotate(avg_rating=Avg("comments__rating"), total_ratings=Count("comments"))
        .order_by("-avg_rating", "-total_ratings", "name")[:8]
    )

    comments = product.comments.select_related("user").order_by("-created_at")

    if request.method == "POST":
        form = CommentForm(
            request.POST,
            initial={"user": request.user if request.user.is_authenticated else None},
        )
        if form.is_valid():
            rating = form.cleaned_data["rating"]
            text = form.cleaned_data.get("text", "")

            if request.user.is_authenticated:
                # Upsert: update existing comment or create a new one
                comment, created = Comment.objects.get_or_create(
                    product=product,
                    user=request.user,
                    defaults={"rating": rating, "text": text},
                )
                if not created:
                    comment.rating = rating
                    comment.text = text
                    comment.save()
                messages.success(
                    request,
                    "Your rating was {}.".format("submitted" if created else "updated"),
                )
            else:
                # Guest: create a new comment (no uniqueness constraint)
                comment = form.save(commit=False)
                comment.product = product
                comment.save()
                messages.success(request, "Thank you for your rating.")

            url = reverse(
                "product_detail",
                kwargs={"category_slug": category_slug, "pk": product.pk},
            )
            return redirect(f"{url}?submitted=1")
    else:
        # Pre-fill form for authenticated user with existing comment (if any)
        initial = {}
        if request.user.is_authenticated and request.GET.get("submitted") != "1":
            existing = product.comments.filter(user=request.user).first()
            if existing:
                initial = {"rating": existing.rating, "text": existing.text}
        form = CommentForm(initial=initial)

    return render(
        request,
        "product.html",
        {
            "product": product,
            "comments": comments,
            "related_products": related_products,
            "form": form,
        },
    )
