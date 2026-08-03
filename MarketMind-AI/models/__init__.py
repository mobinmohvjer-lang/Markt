"""
models package
---------------
Purpose:
    Houses machine learning / AI models used for prediction and analysis
    (e.g. price forecasting, sentiment classification), including their
    training, evaluation, and inference code.

    This is distinct from `core` entities: `models` contains statistical
    and machine-learning models, while `core` contains business domain
    objects.

Planned contents (future versions):
    - training/: scripts to train models on historical (free) data.
    - inference/: lightweight wrappers to load trained models and
      produce predictions for the `analysis` layer.
    - artifacts/: (gitignored) local storage for trained model weights.

Currently empty: no trading logic implemented yet.
"""
