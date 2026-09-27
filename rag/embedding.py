from pathlib import Path
import threading
import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer
from backend.contracts import WorkbenchError
from backend.settings import EMBEDDING_REVISION

QUERY_PREFIX = 'Represent this sentence for searching relevant passages: '


def normalize_output(output):
    vectors = np.asarray(output)
    if vectors.ndim == 3:
        vectors = vectors[:, 0, :]
    if vectors.ndim != 2 or vectors.shape[1] != 384:
        raise WorkbenchError('embedding_unavailable', 'Unexpected embedding dimensions')
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    if not np.isfinite(vectors).all() or np.any(norms == 0):
        raise WorkbenchError('embedding_unavailable', 'Invalid embedding output')
    return (vectors / norms).astype(np.float32)


class Embedder:
    revision = EMBEDDING_REVISION

    def __init__(self, model_dir: Path):
        model_dir = Path(model_dir)
        paths = [model_dir / 'onnx/model.onnx', model_dir / 'tokenizer.json']
        if not all(p.is_file() for p in paths):
            raise WorkbenchError('embedding_unavailable', 'Local embedding files missing; run setup-embeddings.py first')
        try:
            self.tokenizer = Tokenizer.from_file(str(paths[1]))
            self.tokenizer.no_padding()
            self.tokenizer.no_truncation()
            self._batch_tokenizer = Tokenizer.from_file(str(paths[1]))
            self._batch_tokenizer.no_truncation()
            self._batch_tokenizer.enable_padding(pad_id=0, pad_token='[PAD]')
            options = ort.SessionOptions()
            options.intra_op_num_threads = 2
            options.inter_op_num_threads = 1
            self.session = ort.InferenceSession(str(paths[0]), sess_options=options, providers=['CPUExecutionProvider'])
            self._lock = threading.Lock()
        except Exception as exc:
            raise WorkbenchError('embedding_unavailable', 'Could not load local embedding assets') from exc

    def encode(self, texts: list[str], query=False):
        if not texts:
            return np.empty((0, 384), dtype=np.float32)
        results = []
        with self._lock:
            for start in range(0, len(texts), 8):
                batch = [(QUERY_PREFIX if query else '') + text for text in texts[start:start+8]]
                if any(len(self.tokenizer.encode(text).ids) > 512 for text in batch):
                    raise WorkbenchError('question_too_long' if query else 'embedding_input_too_long', 'Embedding input exceeds 512 tokens')
                encoded = self._batch_tokenizer.encode_batch(batch)
                values = {
                    'input_ids': np.array([e.ids for e in encoded], dtype=np.int64),
                    'attention_mask': np.array([e.attention_mask for e in encoded], dtype=np.int64),
                    'token_type_ids': np.array([e.type_ids for e in encoded], dtype=np.int64),
                }
                feed = {i.name: values[i.name] for i in self.session.get_inputs()}
                output = self.session.run(None, feed)[0]
                results.append(normalize_output(output))
        return np.concatenate(results)
