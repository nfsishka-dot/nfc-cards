from FlashSQL import Client


def main() -> None:
    db = Client("database.db")

    # FlashSQL doesn't document iteration here; try common methods safely.
    keys = None
    for attr in ("keys", "all", "list", "__iter__"):
        if hasattr(db, attr):
            try:
                maybe = getattr(db, attr)()
                if maybe is not None:
                    keys = list(maybe)
                    break
            except TypeError:
                # __iter__ isn't callable
                pass
            except Exception:
                pass

    if keys is None:
        # last resort: try iter(db)
        try:
            keys = list(db)  # type: ignore[arg-type]
        except Exception:
            keys = []

    print("keys_count", len(keys))
    print("first_keys", keys[:5])

    if not keys:
        return

    font_hits = []
    for k in keys:
        post = db.get(k)
        if not isinstance(post, dict):
            continue
        content = post.get("content", "") or ""
        if "ql-font" in content:
            font_hits.append(k)

    print("ql_font_posts", len(font_hits))
    if font_hits:
        k = font_hits[-1]
        post = db.get(k)
        content = post.get("content", "") if isinstance(post, dict) else ""
        print("sample_ql_font_key", k)
        idx = content.find("ql-font")
        snippet = content[max(0, idx - 120) : idx + 300]
        print("ql_font_snippet", snippet.replace("\n", " "))
    else:
        sample_key = keys[-1]
        post = db.get(sample_key)
        content = post.get("content", "") if isinstance(post, dict) else ""
        print("sample_key", sample_key)
        print("content_snippet", content[:800].replace("\n", " "))


if __name__ == "__main__":
    main()

