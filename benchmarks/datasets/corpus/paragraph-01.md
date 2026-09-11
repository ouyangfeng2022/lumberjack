# Long paragraph

The fallback order starts at a paragraph boundary, continues at a line break,
then chooses a sentence boundary before considering words and finally a hard
split. This deliberately long paragraph repeats the fallback order so a small
budget must exercise multiple safe boundaries. The sentence boundary remains
preferable to a word boundary whenever it produces a usable prefix.
