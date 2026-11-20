# Copyright 2020 The HuggingFace Datasets Authors and the current dataset script contributor.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""RepoBench: Benchmarking Repository-Level Code Auto-Completion Systems"""

import gzip
import pickle
import textwrap
import datasets

_CITATION = """\
@misc{liu2023repobench,
      title={RepoBench: Benchmarking Repository-Level Code Auto-Completion Systems}, 
      author={Tianyang Liu and Canwen Xu and Julian McAuley},
      year={2023},
      eprint={2306.03091},
      archivePrefix={arXiv},
      primaryClass={cs.CL}
}
"""

_DESCRIPTION = """\
RepoBench is a dataset that benchmarks repository-level code auto-completion systems.

RepoBench-R denotes RepoBench for Retrieval, which is a sub-task of RepoBench, 
aiming to evaluate the ability of code auto-completion systems to retrieve 
relevant code snippets for next-line code completion.
"""

_HOMEPAGE = "https://github.com/Leolty/repobench"

_LICENSE = "Apache License 2.0"

_URLs = {
    "java_cff": "https://huggingface.co/datasets/tianyang/repobench-r/resolve/main/data/java_cff.gz",
    "java_cfr": "https://huggingface.co/datasets/tianyang/repobench-r/resolve/main/data/java_cfr.gz",
    "python_cff": "https://huggingface.co/datasets/tianyang/repobench-r/resolve/main/data/python_cff.gz",
    "python_cfr": "https://huggingface.co/datasets/tianyang/repobench-r/resolve/main/data/python_cfr.gz"
}

class RepoBenchR(datasets.GeneratorBasedBuilder):
    """RepoBench"""

    VERSION = datasets.Version("1.0.0")

    BUILDER_CONFIGS = [
        datasets.BuilderConfig(
            name="python_cff",
            description=textwrap.dedent(
                """
                cff: cross_file_first -> mask the the line that a cross-file module is first used
                """
            )
        ),
        datasets.BuilderConfig(
            name="python_cfr",
            description=textwrap.dedent(
                """
                cfr: cross_file_random -> mask a random line that a cross-file module is used (not the first time)
                """
            )
        ),
        datasets.BuilderConfig(
            name="java_cff",
            description=textwrap.dedent(
                """
                cff: cross_file_first -> mask the the line that a cross-file module is first used
                """
            )
        ),
        datasets.BuilderConfig(
            name="java_cfr",
            description=textwrap.dedent(
                """
                cfr: cross_file_random -> mask a random line that a cross-file module is used (not the first time)
                """
            )
        )
    ]

    def _info(self):
        features = datasets.Features(
            {
                "repo_name": datasets.Value("string"),
                "file_path": datasets.Value("string"),
                "context": [datasets.Value("string")],
                "import_statement": datasets.Value("string"),
                "code": datasets.Value("string"),
                "next_line": datasets.Value("string"),
                "gold_snippet_index": datasets.Value("int32")
            }
        )

        return datasets.DatasetInfo(
            description=_DESCRIPTION,
            features=features,
            homepage=_HOMEPAGE,
            license=_LICENSE,
            citation=_CITATION,
        )

    def _split_generators(self, dl_manager):
        """Returns SplitGenerators."""
        config_urls = _URLs[self.config.name]
        data_dir = dl_manager.download(config_urls)

        return [
            datasets.SplitGenerator(
                name=datasets.Split("train_easy"),
                gen_kwargs={"data_dir": data_dir, "split": "train_easy"},
            ),
            datasets.SplitGenerator(
                name=datasets.Split("train_hard"),
                gen_kwargs={"data_dir": data_dir, "split": "train_hard"},
            ),
            datasets.SplitGenerator(
                name=datasets.Split("test_easy"),
                gen_kwargs={"data_dir": data_dir, "split": "test_easy"},
            ),
            datasets.SplitGenerator(
                name=datasets.Split("test_hard"),
                gen_kwargs={"data_dir": data_dir, "split": "test_hard"},
            )
        ]

    def _generate_examples(self, data_dir, split):
        """ Yields examples. """
        with gzip.open(data_dir, "rb") as f:
            data = pickle.load(f)
        
        subset, level = split.split("_")

        for i, example in enumerate(data[subset][level]):
            yield i, {
                "repo_name": example["repo_name"],
                "file_path": example["file_path"],
                "context": example["context"],
                "import_statement": example["import_statement"],
                "code": example["code"],
                "next_line": example["next_line"],
                "gold_snippet_index": example["golden_snippet_index"]
            }

