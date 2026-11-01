"""Sequence models: LSTM and CNN-LSTM on 24-hour windows.

Requires PyTorch. This module is imported lazily and `train_sequence_model`
returns None when torch is missing, so the rest of the pipeline never breaks
because of an optional 2 GB dependency.

The point of this model is not to win - on tabular data with strong lag
features a GBDT usually wins. The point is to answer the question "does
temporal structure beyond the engineered lags help?", and to have a defensible
deep baseline in the comparison table.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..utils import get_logger

log = get_logger("pm25.deep")

try:  # optional dependency
    import torch
    from torch import nn
    from torch.utils.data import DataLoader, TensorDataset
    HAS_TORCH = True
except Exception:  # pragma: no cover
    torch = None
    nn = None
    DataLoader = None
    TensorDataset = None
    HAS_TORCH = False


def is_available() -> bool:
    return HAS_TORCH


# ---------------------------------------------------------------------------
# Sequence construction
# ---------------------------------------------------------------------------

def build_sequences(df: pd.DataFrame, features: list[str], seq_len: int = 24):
    """Sliding windows per station. Returns (X, y, row_index)."""
    xs, ys, idx = [], [], []
    for _, group in df.groupby("station", sort=False):
        group = group.sort_values("time")
        arr = group[features].to_numpy(dtype=np.float32)
        target = group["y"].to_numpy(dtype=np.float32)
        if len(arr) < seq_len:
            continue
        positions = np.arange(seq_len - 1, len(arr))
        windows = np.stack([arr[p - seq_len + 1 : p + 1] for p in positions])
        xs.append(windows)
        ys.append(target[positions])
        idx.append(group.index.to_numpy()[positions])

    if not xs:
        return np.empty((0, seq_len, len(features)), np.float32), np.empty(0, np.float32), np.empty(0, int)

    return np.concatenate(xs), np.concatenate(ys), np.concatenate(idx)


def _standardise(train_X: np.ndarray, other: np.ndarray):
    mean = train_X.reshape(-1, train_X.shape[-1]).mean(axis=0)
    std = train_X.reshape(-1, train_X.shape[-1]).std(axis=0)
    std = np.where(std < 1e-6, 1.0, std)
    return (train_X - mean) / std, (other - mean) / std, mean, std


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

if HAS_TORCH:

    class CNNLSTM(nn.Module):
        """Optional 1-D conv front end, then an LSTM, then a linear head."""

        def __init__(self, n_features: int, hidden: int = 64, layers: int = 1,
                     dropout: float = 0.15, use_cnn: bool = True):
            super().__init__()
            self.use_cnn = use_cnn
            if use_cnn:
                self.conv = nn.Conv1d(n_features, hidden, kernel_size=3, padding=1)
                self.act = nn.ReLU()
                lstm_input = hidden
            else:
                lstm_input = n_features

            self.lstm = nn.LSTM(
                lstm_input, hidden, num_layers=layers,
                batch_first=True, dropout=dropout if layers > 1 else 0.0,
            )
            self.head = nn.Sequential(
                nn.Dropout(dropout),
                nn.Linear(hidden, 32),
                nn.ReLU(),
                nn.Linear(32, 1),
            )

        def forward(self, x):
            # x: (batch, seq, features)
            if self.use_cnn:
                x = x.transpose(1, 2)              # (batch, features, seq)
                x = self.act(self.conv(x))
                x = x.transpose(1, 2)              # (batch, seq, hidden)
            out, _ = self.lstm(x)
            return self.head(out[:, -1, :]).squeeze(-1)

else:  # pragma: no cover
    CNNLSTM = None


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def train_sequence_model(
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    features: list[str],
    seq_len: int = 24,
    epochs: int = 12,
    batch_size: int = 256,
    lr: float = 1e-3,
    use_cnn: bool = True,
    seed: int = 42,
) -> np.ndarray | None:
    """Returns predictions aligned to test_df rows, or None if torch is absent."""
    if not HAS_TORCH:
        log.warning("PyTorch not installed - skipping sequence model. `pip install torch` to enable.")
        return None

    X_tr, y_tr, _ = build_sequences(train_df, features, seq_len)
    X_te, y_te, idx_te = build_sequences(test_df, features, seq_len)

    if len(X_tr) == 0 or len(X_te) == 0:
        log.warning("Not enough rows to build %d-hour sequences - skipping.", seq_len)
        return None

    X_tr, X_te, _, _ = _standardise(X_tr, X_te)
    y_mean, y_std = float(y_tr.mean()), float(y_tr.std() or 1.0)
    y_tr_n = (y_tr - y_mean) / y_std

    # Time-ordered validation tail, never a random split.
    cut = int(len(X_tr) * 0.9)
    train_ds = TensorDataset(torch.from_numpy(X_tr[:cut]), torch.from_numpy(y_tr_n[:cut]))
    val_ds = TensorDataset(torch.from_numpy(X_tr[cut:]), torch.from_numpy(y_tr_n[cut:]))
    train_dl = DataLoader(train_ds, batch_size=batch_size, shuffle=True, drop_last=False)
    val_dl = DataLoader(val_ds, batch_size=batch_size, shuffle=False)

    torch.manual_seed(seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = CNNLSTM(n_features=X_tr.shape[-1], use_cnn=use_cnn).to(device)

    optimiser = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    loss_fn = nn.HuberLoss()

    best_val, best_state, patience = float("inf"), None, 0

    for epoch in range(1, epochs + 1):
        model.train()
        running = 0.0
        for xb, yb in train_dl:
            xb, yb = xb.to(device), yb.to(device)
            optimiser.zero_grad()
            loss = loss_fn(model(xb), yb)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimiser.step()
            running += float(loss) * len(xb)
        train_loss = running / max(1, len(train_ds))

        model.eval()
        val_loss, val_n = 0.0, 0
        with torch.no_grad():
            for xb, yb in val_dl:
                xb, yb = xb.to(device), yb.to(device)
                val_loss += float(loss_fn(model(xb), yb)) * len(xb)
                val_n += len(xb)
        val_loss = val_loss / max(1, val_n)

        log.info("epoch %2d  train %.4f  val %.4f", epoch, train_loss, val_loss)

        if val_loss < best_val - 1e-4:
            best_val, patience = val_loss, 0
            best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}
        else:
            patience += 1
            if patience >= 3:
                log.info("early stop at epoch %d", epoch)
                break

    if best_state is not None:
        model.load_state_dict(best_state)

    model.eval()
    with torch.no_grad():
        preds = model(torch.from_numpy(X_te).to(device)).cpu().numpy()

    preds = preds * y_std + y_mean

    # Re-align onto the full test frame: rows before the first full window
    # have no prediction and stay NaN.
    aligned = np.full(len(test_df), np.nan)
    positions = test_df.index.get_indexer(idx_te)
    valid = positions >= 0
    aligned[positions[valid]] = preds[valid]
    return aligned
