# Polyglot Snippets

The same task in several languages, kept in one place for teaching.

## Python

```python
def fizzbuzz(n: int) -> list[str]:
    out = []
    for i in range(1, n + 1):
        if i % 15 == 0:
            out.append("fizzbuzz")
        elif i % 3 == 0:
            out.append("fizz")
        elif i % 5 == 0:
            out.append("buzz")
        else:
            out.append(str(i))
    return out
```

## Rust

```rust
fn fizzbuzz(n: u32) -> Vec<String> {
    (1..=n)
        .map(|i| match (i % 3, i % 5) {
            (0, 0) => "fizzbuzz".into(),
            (0, _) => "fizz".into(),
            (_, 0) => "buzz".into(),
            _ => i.to_string(),
        })
        .collect()
}
```

## Shell

```bash
for i in $(seq 1 30); do
  if [ $((i % 15)) -eq 0 ]; then echo fizzbuzz
  elif [ $((i % 3)) -eq 0 ]; then echo fizz
  elif [ $((i % 5)) -eq 0 ]; then echo buzz
  else echo "$i"; fi
done
```

## Notes

Rust matches on the pair of remainders, which keeps the branches flat. The
shell version is deliberately naive; do not use it as a style reference.
