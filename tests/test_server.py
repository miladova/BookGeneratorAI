import json
import os
import tempfile
import unittest

import server


class TestDiscoverBooks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.books = os.path.join(self.tmp.name, "books")
        self.legacy = os.path.join(self.tmp.name, "output")
        os.makedirs(self.books)
        os.makedirs(self.legacy)

    def make_book(self, name, title=None, author=None, chapters=1, docx=True, epub=True):
        book_dir = os.path.join(self.books, name)
        os.makedirs(os.path.join(book_dir, "manuscript"))
        if title:
            with open(os.path.join(book_dir, "book.json"), "w", encoding="utf-8") as f:
                json.dump({"title": title, "author": author, "genre": "fiction", "language": "english"}, f)
        if docx:
            with open(os.path.join(book_dir, f"{name}.docx"), "wb") as f:
                f.write(b"PK")
        if epub:
            with open(os.path.join(book_dir, f"{name}.epub"), "wb") as f:
                f.write(b"PK")
        with open(os.path.join(book_dir, "state.db"), "wb"):
            pass
        for i in range(1, chapters + 1):
            with open(os.path.join(book_dir, "manuscript", f"chapter_{i:02d}.md"), "w", encoding="utf-8") as f:
                f.write(f"# Chapter {i}\n")
        return book_dir

    def test_finds_completed_and_incomplete_books(self):
        self.make_book("The_Ledger", title="The Ledger", author="A. Writer", chapters=2)
        self.make_book("Unfinished", title="Unfinished", chapters=1, docx=False, epub=False)
        os.makedirs(os.path.join(self.books, "not_a_book"))

        records = {r["title"]: r for r in server.discover_books(self.books, self.legacy)}

        self.assertEqual(set(records), {"The Ledger", "Unfinished"})
        self.assertEqual(records["The Ledger"]["status"], "completed")
        self.assertEqual(records["The Ledger"]["progress_percent"], 100)
        self.assertEqual(records["The Ledger"]["author"], "A. Writer")
        self.assertTrue(records["The Ledger"]["docx_path"].endswith(".docx"))
        self.assertTrue(records["The Ledger"]["epub_path"].endswith(".epub"))
        self.assertEqual(records["The Ledger"]["chapters"], ["chapter_01.md", "chapter_02.md"])
        self.assertEqual(records["Unfinished"]["status"], "incomplete")
        self.assertEqual(records["Unfinished"]["progress_percent"], 0)
        self.assertEqual(records["Unfinished"]["docx_path"], "")

    def test_book_without_manifest_uses_folder_name(self):
        self.make_book("Folder_Title", docx=True, epub=False)
        record = server.discover_books(self.books, self.legacy)[0]
        self.assertEqual(record["title"], "Folder Title")
        self.assertEqual(record["author"], "Unknown")

    def test_legacy_output_folder_is_still_listed(self):
        with open(os.path.join(self.legacy, "Old_Book.docx"), "wb") as f:
            f.write(b"PK")
        with open(os.path.join(self.legacy, "chapter_01.md"), "w", encoding="utf-8") as f:
            f.write("# Chapter 1\n")

        records = server.discover_books(self.books, self.legacy)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["title"], "Old Book")
        self.assertEqual(records[0]["status"], "completed")
        self.assertEqual(records[0]["chapters"], ["chapter_01.md"])

    def test_job_ids_are_stable_and_unique(self):
        first = self.make_book("One", title="One")
        second = self.make_book("Two", title="Two")
        ids = {r["job_id"] for r in server.discover_books(self.books, self.legacy)}
        self.assertEqual(len(ids), 2)
        self.assertEqual(server._saved_job_id(first), server._saved_job_id(first))
        self.assertNotEqual(server._saved_job_id(first), server._saved_job_id(second))


if __name__ == "__main__":
    unittest.main()
