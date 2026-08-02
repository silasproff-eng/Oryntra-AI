import 'dart:async';

import 'package:google_mobile_ads/google_mobile_ads.dart';

import '../app_config.dart';

class InterstitialAdService {
  InterstitialAd? _ad;
  bool _isLoading = false;
  bool _isDisposed = false;
  int _successfulScans = 0;

  void initialize() {
    unawaited(_load());
  }

  Future<void> recordSuccessfulScan() async {
    if (_isDisposed) return;

    _successfulScans++;
    if ((_successfulScans - 1) % 3 != 0) {
      if (_ad == null) unawaited(_load());
      return;
    }

    final ad = _ad;
    if (ad == null) {
      unawaited(_load());
      return;
    }

    _ad = null;
    ad.fullScreenContentCallback = FullScreenContentCallback(
      onAdDismissedFullScreenContent: (dismissedAd) {
        dismissedAd.dispose();
        unawaited(_load());
      },
      onAdFailedToShowFullScreenContent: (failedAd, error) {
        failedAd.dispose();
        unawaited(_load());
      },
    );
    ad.show();
  }

  Future<void> _load() async {
    if (_isDisposed || _isLoading || _ad != null) return;
    _isLoading = true;

    await InterstitialAd.load(
      adUnitId: AppConfig.interstitialAdUnitId,
      request: const AdRequest(),
      adLoadCallback: InterstitialAdLoadCallback(
        onAdLoaded: (ad) {
          _isLoading = false;
          if (_isDisposed) {
            ad.dispose();
            return;
          }
          _ad = ad;
        },
        onAdFailedToLoad: (error) {
          _isLoading = false;
        },
      ),
    );
  }

  void dispose() {
    _isDisposed = true;
    _ad?.dispose();
    _ad = null;
  }
}
