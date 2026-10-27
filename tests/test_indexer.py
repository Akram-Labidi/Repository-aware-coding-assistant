import unittest
from repocortex.indexer.ast_parser import PythonASTParser, PolyglotStructuralParser
from repocortex.indexer.bm25 import BM25Index, CodeTokenizer
from repocortex.indexer.symbol_graph import SymbolGraph
from repocortex.core.types import Symbol, SymbolKind


class TestASTParser(unittest.TestCase):
    def test_python_ast_extraction(self):
        code = """
import os
from math import sqrt

def helper_fn(val):
    '''A helper function.'''
    return sqrt(val)

class Calculator:
    '''Calculates values.'''
    def __init__(self, offset=0):
        self.offset = offset

    def compute(self, x):
        return helper_fn(x) + self.offset
"""
        parser = PythonASTParser("calc.py", code)
        symbols, imports = parser.parse()

        self.assertIn("os", imports)
        self.assertIn("math.sqrt", imports)

        sym_names = {s.name: s for s in symbols}
        self.assertIn("helper_fn", sym_names)
        self.assertIn("Calculator", sym_names)
        self.assertIn("compute", sym_names)

        # Check call graph extraction
        compute_sym = sym_names["compute"]
        self.assertIn("helper_fn", compute_sym.callees)

    def test_polyglot_ts_extraction(self):
        code = """
import { useState } from 'react';

export function calculateTotal(items: number[]): number {
    return items.reduce((a, b) => a + b, 0);
}

export class OrderService {
    processOrder(id: string) {}
}
"""
        parser = PolyglotStructuralParser("service.ts", code, "typescript")
        symbols, imports = parser.parse()
        sym_names = [s.name for s in symbols]
        self.assertIn("calculateTotal", sym_names)
        self.assertIn("OrderService", sym_names)


class TestBM25(unittest.TestCase):
    def test_code_tokenizer(self):
        tokens = CodeTokenizer.tokenize("def calculateTotalRevenue_USD():")
        self.assertIn("calculate", tokens)
        self.assertIn("total", tokens)
        self.assertIn("revenue", tokens)
        self.assertIn("usd", tokens)

    def test_bm25_search_ranking(self):
        idx = BM25Index()
        idx.index_documents({
            "doc1": "def calculate_discount(price, tier): return price * 0.9",
            "doc2": "class DatabaseConnection: def connect(self): pass",
            "doc3": "def print_invoice(customer): pass",
        })
        results = idx.search("discount price")
        self.assertTrue(len(results) > 0)
        self.assertEqual(results[0][0], "doc1")


class TestSymbolGraph(unittest.TestCase):
    def test_pagerank_computation(self):
        graph = SymbolGraph()
        s1 = Symbol("core_util", "core_util", SymbolKind.FUNCTION, "util.py", 1, 10)
        s2 = Symbol("caller_a", "caller_a", SymbolKind.FUNCTION, "a.py", 1, 10, callees=["core_util"])
        s3 = Symbol("caller_b", "caller_b", SymbolKind.FUNCTION, "b.py", 1, 10, callees=["core_util"])

        graph.add_symbol(s1)
        graph.add_symbol(s2)
        graph.add_symbol(s3)
        graph.build_edges()

        # core_util has incoming calls from caller_a and caller_b, so its PageRank should be higher
        pr_util = graph.get_centrality("util.py", "core_util")
        pr_caller = graph.get_centrality("a.py", "caller_a")
        self.assertGreater(pr_util, pr_caller)


if __name__ == "__main__":
    unittest.main()
