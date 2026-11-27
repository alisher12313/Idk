from pathlib import Path
from fastapi.staticfiles import StaticFiles
from fastapi import FastAPI, Request, HTTPException, status, Depends
from fastapi.templating import Jinja2Templates
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .models import User, Post
from .schemas import PostResponse, PostCreate, UserResponse, UserCreate, PostUpdate, UserUpdate

from typing import Annotated
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database.connection_settings import Base, engine, get_db

Base.metadata.create_all(bind=engine)

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI()
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name='static')
app.mount('/media', StaticFiles(directory=BASE_DIR / 'media'), name='media')
templates = Jinja2Templates(directory=BASE_DIR / "templates")


# ============================================================
# HTML pages (hidden from /docs)
# ============================================================

@app.get("/", include_in_schema=False, name='home')
@app.get("/posts", include_in_schema=False, name='posts')
def home(request: Request, db: Annotated[Session, Depends(get_db)]):
    result = db.execute(select(Post))
    posts = result.scalars().all()
    return templates.TemplateResponse(
        request,
        "home.html",
        {"posts": posts, "title": "Home"},
    )

@app.get("/posts/{post_id}", include_in_schema=False)
def post_page(request: Request, post_id: int, db: Annotated[Session, Depends(get_db)]):
    result = db.execute(select(Post).where(Post.id == post_id))
    post = result.scalars().first()
    if post:
        return templates.TemplateResponse(
            request,
            "post.html",
            {"post": post, "title": post.title[:50]},
            )

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Post not found"
    )

@app.get("/users/{user_id}/posts", include_in_schema=False, name="user_posts")
def user_posts_page(
    request: Request,
    user_id: int,
    db: Annotated[Session, Depends(get_db)],
):
    result = db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    result = db.execute(select(Post).where(Post.user_id == user_id))
    posts = result.scalars().all()
    return templates.TemplateResponse(
        request,
        "user_posts.html",
        {"posts": posts, "user": user, "title": f"{user.username}'s Posts"},
    )


# ============================================================
# API: Users
# ============================================================

@app.post("/api/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED, tags=["users"])
def create_user(user: UserCreate, db: Annotated[Session, Depends(get_db)]):
    result = db.execute(select(User).where(User.username == user.username))
    existing_user = result.scalars().first()
    if existing_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already exists")

    result = db.execute(select(User).where(User.email == user.email))
    existing_user = result.scalars().first()
    if existing_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already exists")

    new_user = User(
        username=user.username,
        email=user.email
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user

@app.get("/api/users/{user_id}", response_model=UserResponse, tags=["users"])
def get_user(user_id: int, db: Annotated[Session, Depends(get_db)]):
    result = db.execute(
        select(User).where(User.id == user_id),
    )
    user = result.scalars().first()

    if user:
        return user

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

@app.get("/api/users/{user_id}/posts", response_model=list[PostResponse], tags=["users"])
def get_posts_by_user(user_id: int, db: Annotated[Session, Depends(get_db)]):
    result = db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    result = db.execute(select(Post).where(Post.user_id == user_id))
    posts = result.scalars().all()
    return posts

@app.put("/api/users/{user_id}", response_model=UserResponse, tags=['users'])
@app.patch("/api/users/{user_id}", response_model=UserResponse, tags=['users'])
def update_user_full(user_id: int, update_model: UserUpdate, db: Annotated[Session, Depends(get_db)]):
    user: User = db.execute(select(User).where(User.id == user_id)).scalars().first()
    if not user:
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    if update_model.username is not None and update_model.username != user.username:
        existing_mail = db.execute(select(User).where(User.username == update_model.username)).scalars().first()
        if existing_mail:
            return HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Username already exists"
            )

    for key, value in update_model.model_dump(exclude_unset=True).items():
        setattr(user, key, value)

    db.commit()
    db.refresh(user)
    return user

@app.delete('/api/users/{user_id}', status_code=status.HTTP_204_NO_CONTENT, tags=['users'])
def delete_user(user_id: int, db: Annotated[Session, Depends(get_db)]):
    user = db.execute(select(User).where(User.id == user_id)).scalars().first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    db.delete(user)
    db.commit()
# ============================================================
# API: Posts
# ============================================================

@app.post("/api/posts", response_model=PostResponse, status_code=status.HTTP_201_CREATED, tags=["posts"])
def create_post(post: PostCreate, db: Annotated[Session, Depends(get_db)]):
    user = db.execute(select(User).where(User.id == post.user_id)).scalars().first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    new_post = Post(
        title=post.title,
        content=post.content,
        user_id=post.user_id
    )

    db.add(new_post)
    db.commit()
    db.refresh(new_post)

    return new_post

@app.get("/api/posts", response_model=list[PostResponse], tags=["posts"])
def get_posts(db: Annotated[Session, Depends(get_db)]):
    return db.execute(select(Post)).scalars().all()

@app.get("/api/posts/{post_id}", response_model=PostResponse, tags=["posts"])
def get_post(post_id: int, db: Annotated[Session, Depends(get_db)]):
    post = db.execute(select(Post).where(Post.id == post_id)).scalars().first()
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    return post

@app.put("/api/posts/{post_id}", response_model=PostResponse, tags=["posts"])
def update_post_full(post_id: int, post_data: PostCreate, db: Annotated[Session, Depends(get_db)]):
    post = db.execute(select(Post).where(Post.id == post_id)).scalars().first()
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    if post_data.user_id != post.user_id:
        user = db.execute(select(User).where(User.id == post_data.user_id)).scalars().first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail='User not found'
            )
    post.title = post_data.title
    post.content = post_data.content
    post.user_id = post_data.user_id

    db.commit()
    db.refresh(post)

    return post

@app.patch("/api/posts/{post_id}", response_model=PostResponse, tags=["posts"])
def update_post_partial(post_id: int, post_data: PostUpdate, db: Annotated[Session, Depends(get_db)]):
    post = db.execute(select(Post).where(Post.id == post_id)).scalars().first()

    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    updated_data = post_data.model_dump(exclude_unset=True)
    for field, value in updated_data.items():
        setattr(post, field, value)

    db.commit()
    db.refresh(post)

    return post

@app.delete("/api/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT, tags=['posts'])
def delete_post_on_id(post_id: int, db: Annotated[Session, Depends(get_db)]):
    post = db.execute(select(Post).where(Post.id == post_id)).scalars().first()
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found"
        )

    db.delete(post)
    db.commit()

# ============================================================
# Exception handlers
# ============================================================

@app.exception_handler(StarletteHTTPException)
def general_http_exception_handler(request: Request, exception: StarletteHTTPException):
    message = (
        exception.detail if exception.detail else "An error occurred. Please check your request again"
    )

    if request.url.path.startswith("/api"):
        return JSONResponse(
            status_code=exception.status_code,
            content={'detail': message}
        )

    return templates.TemplateResponse(
        request, "error.html", {
            "status_code": exception.status_code,
            "title": exception.status_code,
            "message": message
        },
        status_code=exception.status_code
    )

@app.exception_handler(RequestValidationError)
def validation_exception_handler(request: Request, exception: RequestValidationError):
    if request.url.path.startswith('/api'):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={"detail": exception.errors()}
        )

    return templates.TemplateResponse(
        request,
        "error.html",
        {
            "status_code": status.HTTP_422_UNPROCESSABLE_CONTENT,
            "title": status.HTTP_422_UNPROCESSABLE_CONTENT,
            "message": "Invalid request. Please check your input and try again"
        },
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT
    )