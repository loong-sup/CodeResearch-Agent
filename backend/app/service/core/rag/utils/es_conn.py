#
#  Copyright 2025 The InfiniFlow Authors. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#

import logging
import re
import time
import os
import json

import copy
from elasticsearch import Elasticsearch
from elasticsearch_dsl import Q, Search
from service.core.rag.utils import singleton
from service.core.api.utils.file_utils import get_project_base_directory
from service.core.rag.utils.doc_store_conn import MatchExpr, OrderByExpr, MatchTextExpr, MatchDenseExpr, FusionExpr
from service.core.rag.nlp import is_english
from dotenv import load_dotenv
load_dotenv()

ATTEMPT_TIME = 2
PAGERANK_FLD = "pagerank_fea"
TAG_FLD = "tag_feas"
BULK_DOCS_PER_BATCH = 100
BULK_BYTES_PER_BATCH = 5 * 1024 * 1024

logger = logging.getLogger('es_conn')
ES_URL = os.getenv("ES_URL")

@singleton
class ESConnection():
    def __init__(self):
        self.info = {}
        logger.info(f"Use Elasticsearch  localhost as the doc engine.")
        self.es = Elasticsearch(
            ES_URL,  # Elasticsearch 主机地址
            basic_auth=("elastic", "infini_rag_flow"),  # 用户名和密码
            verify_certs=False,  # 禁用 SSL 证书验证
            timeout=600
        )

        fp_mapping = os.path.join(get_project_base_directory(), "conf", "mapping.json")
        self.mapping = json.load(open(fp_mapping, "r"))


    """
    Helper functions for search result
    """

    def getTotal(self, res):
        if isinstance(res["hits"]["total"], type({})):
            return res["hits"]["total"]["value"]
        return res["hits"]["total"]

    def getChunkIds(self, res):
        return [d["_id"] for d in res["hits"]["hits"]]
    

    def getHighlight(self, res, keywords: list[str], fieldnm: str):
        ans = {}
        for d in res["hits"]["hits"]:
            hlts = d.get("highlight")
            if not hlts:
                continue
            txt = "...".join([a for a in list(hlts.items())[0][1]])
            if not is_english(txt.split()):
                ans[d["_id"]] = txt
                continue

            txt = d["_source"][fieldnm]
            txt = re.sub(r"[\r\n]", " ", txt, flags=re.IGNORECASE | re.MULTILINE)
            txts = []
            for t in re.split(r"[.?!;\n]", txt):
                for w in keywords:
                    t = re.sub(r"(^|[ .?/'\"\(\)!,:;-])(%s)([ .?/'\"\(\)!,:;-])" % re.escape(w), r"\1<em>\2</em>\3", t,
                               flags=re.IGNORECASE | re.MULTILINE)
                if not re.search(r"<em>[^<>]+</em>", t, flags=re.IGNORECASE | re.MULTILINE):
                    continue
                txts.append(t)
            ans[d["_id"]] = "...".join(txts) if txts else "...".join([a for a in list(hlts.items())[0][1]])

        return ans
    

    def getAggregation(self, res, fieldnm: str):
        agg_field = "aggs_" + fieldnm
        if "aggregations" not in res or agg_field not in res["aggregations"]:
            return list()
        bkts = res["aggregations"][agg_field]["buckets"]
        return [(b["key"], b["doc_count"]) for b in bkts]

    def getFields(self, res, fields: list[str]) -> dict[str, dict]:
        res_fields = {}
        if not fields:
            return {}
        for d in self.__getSource(res):
            m = {n: d.get(n) for n in fields if d.get(n) is not None}
            for n, v in m.items():
                if isinstance(v, list):
                    m[n] = v
                    continue
                if not isinstance(v, str):
                    m[n] = str(m[n])
                # if n.find("tks") > 0:
                #     m[n] = rmSpace(m[n])

            if m:
                res_fields[d["id"]] = m
        return res_fields


    def __getSource(self, res):
        rr = []
        for d in res["hits"]["hits"]:
            d["_source"]["id"] = d["_id"]
            d["_source"]["_score"] = d["_score"]
            rr.append(d["_source"])
        return rr

    """
    Database operations
    """
    def insert(self, documents: list[dict], indexName: str, knowledgebaseId: str = None) -> list[str]:
        # Refers to https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-bulk.html
        def iter_document_batches():
            batch = []
            batch_bytes = 0
            for d in documents:
                assert "_id" not in d
                assert "id" in d
                estimated_bytes = len(json.dumps(d, ensure_ascii=False, default=str).encode("utf-8"))
                if batch and (
                    len(batch) >= BULK_DOCS_PER_BATCH
                    or batch_bytes + estimated_bytes > BULK_BYTES_PER_BATCH
                ):
                    yield batch
                    batch = []
                    batch_bytes = 0
                batch.append(d)
                batch_bytes += estimated_bytes
            if batch:
                yield batch

        errors = []
        for doc_batch in iter_document_batches():
            operations = []
            for d in doc_batch:
                d_copy = copy.deepcopy(d)
                meta_id = d_copy.pop("id", "")
                operations.append({"index": {"_index": indexName, "_id": meta_id}})
                operations.append(d_copy)

            batch_error = None
            for _ in range(ATTEMPT_TIME):
                try:
                    res = []
                    r = self.es.bulk(
                        index=indexName,
                        operations=operations,
                        refresh=False,
                        timeout="60s",
                    )
                    if re.search(r"False", str(r["errors"]), re.IGNORECASE):
                        batch_error = None
                        break

                    for item in r["items"]:
                        for action in ["create", "delete", "index", "update"]:
                            if action in item and "error" in item[action]:
                                res.append(str(item[action]["_id"]) + ":" + str(item[action]["error"]))
                    if not res:
                        batch_error = None
                        break

                    batch_error = "; ".join(res[:10])
                    logger.warning("ESConnection.insert got item errors: %s", batch_error)
                except Exception as e:
                    batch_error = str(e)
                    logger.warning("ESConnection.insert got exception: %s", batch_error)
                    if re.search(r"(Timeout|time out)", batch_error, re.IGNORECASE):
                        time.sleep(3)
                        continue
                if batch_error:
                    break

            if batch_error:
                errors.append(batch_error)

        return errors

    def delete_by_metadata(self, index_name: str, condition: dict) -> int:
        if not condition:
            return 0

        filters = []
        for key, value in condition.items():
            if isinstance(value, list):
                filters.append({"terms": {key: value}})
            else:
                filters.append({"term": {key: value}})

        query = {"query": {"bool": {"filter": filters}}}
        response = self.es.delete_by_query(
            index=index_name,
            body=query,
            conflicts="proceed",
            refresh=True,
        )
        return int(response.get("deleted", 0))
    

    def search(
            self, selectFields: list[str],
            highlightFields: list[str],
            condition: dict,
            matchExprs: list[MatchExpr],
            orderBy: OrderByExpr,
            offset: int,
            limit: int,
            indexNames: str | list[str],
            knowledgebaseIds: list[str],
            aggFields: list[str] = [],
            rank_feature: dict | None = None
    ):
        """
        Refers to https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl.html
        """
        if isinstance(indexNames, str):
            indexNames = indexNames.split(",")
        assert isinstance(indexNames, list) and len(indexNames) > 0
        assert "_id" not in condition

        bqry = Q("bool", must=[])
        condition["kb_id"] = knowledgebaseIds
        for k, v in condition.items():
            if k == "available_int":
                if v == 0:
                    bqry.filter.append(Q("range", available_int={"lt": 1}))
                else:
                    bqry.filter.append(
                        Q("bool", must_not=Q("range", available_int={"lt": 1})))
                continue
            if not v:
                continue
            if isinstance(v, list):
                bqry.filter.append(Q("terms", **{k: v}))
            elif isinstance(v, str) or isinstance(v, int):
                bqry.filter.append(Q("term", **{k: v}))
            else:
                raise Exception(
                    f"Condition `{str(k)}={str(v)}` value type is {str(type(v))}, expected to be int, str or list.")

        s = Search()
        vector_similarity_weight = 0.5
        for m in matchExprs:
            if isinstance(m, FusionExpr) and m.method == "weighted_sum" and "weights" in m.fusion_params:
                assert len(matchExprs) == 3 and isinstance(matchExprs[0], MatchTextExpr) and isinstance(matchExprs[1],
                                                                                                        MatchDenseExpr) and isinstance(
                    matchExprs[2], FusionExpr)
                weights = m.fusion_params["weights"]
                vector_similarity_weight = float(weights.split(",")[1])
        for m in matchExprs:
            if isinstance(m, MatchTextExpr):
                minimum_should_match = m.extra_options.get("minimum_should_match", 0.0)
                if isinstance(minimum_should_match, float):
                    minimum_should_match = str(int(minimum_should_match * 100)) + "%"
                bqry.must.append(Q("query_string", fields=m.fields,
                                   type="best_fields", query=m.matching_text,
                                   minimum_should_match=minimum_should_match,
                                   boost=1))
                bqry.boost = 1.0 - vector_similarity_weight

            elif isinstance(m, MatchDenseExpr):
                assert (bqry is not None)
                similarity = 0.0
                if "similarity" in m.extra_options:
                    similarity = m.extra_options["similarity"]
                s = s.knn(m.vector_column_name,
                          m.topn,
                          m.topn * 2,
                          query_vector=list(m.embedding_data),
                          filter=bqry.to_dict(),
                          similarity=similarity,
                          )

        if bqry and rank_feature:
            for fld, sc in rank_feature.items():
                if fld != PAGERANK_FLD:
                    fld = f"{TAG_FLD}.{fld}"
                bqry.should.append(Q("rank_feature", field=fld, linear={}, boost=sc))

        if bqry:
            s = s.query(bqry)
        for field in highlightFields:
            s = s.highlight(field)

        if orderBy:
            orders = list()
            for field, order in orderBy.fields:
                order = "asc" if order == 0 else "desc"
                if field in ["page_num_int", "top_int"]:
                    order_info = {"order": order, "unmapped_type": "float",
                                  "mode": "avg", "numeric_type": "double"}
                elif field.endswith("_int") or field.endswith("_flt"):
                    order_info = {"order": order, "unmapped_type": "float"}
                else:
                    order_info = {"order": order, "unmapped_type": "text"}
                orders.append({field: order_info})
            s = s.sort(*orders)

        for fld in aggFields:
            s.aggs.bucket(f'aggs_{fld}', 'terms', field=fld, size=1000000)

        if limit > 0:
            s = s[offset:offset + limit]
        q = s.to_dict()
        logger.debug(f"ESConnection.search {str(indexNames)} query: " + json.dumps(q))

        for i in range(ATTEMPT_TIME):
            try:
                #print(json.dumps(q, ensure_ascii=False))
                res = self.es.search(index=indexNames,
                                     body=q,
                                     timeout="600s",
                                     # search_type="dfs_query_then_fetch",
                                     track_total_hits=True,
                                     _source=True)
                if str(res.get("timed_out", "")).lower() == "true":
                    raise Exception("Es Timeout.")
                logger.debug(f"ESConnection.search {str(indexNames)} res: " + str(res))
                return res
            except Exception as e:
                logger.exception(f"ESConnection.search {str(indexNames)} query: " + str(q))
                if str(e).find("Timeout") > 0:
                    continue
                raise e
        logger.error("ESConnection.search timeout for 3 times!")
        raise Exception("ESConnection.search timeout.")
