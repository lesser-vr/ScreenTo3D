import QtQuick
import DepthSBS.Native 1.0

NativeSurface {
    property bool demand: false
    session: live.nativeSession
    enabledFrame: demand && live.active && !live.stoppingNow && live.hasFrame
    revision: live.frameRevision
}
