import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    id: root
    width: 980
    height: 680
    visible: true
    title: "Escape Bot"
    color: "#111317"

    property string pendingInput: ""

    Component.onCompleted: backendBridge.connectToBackend()

    Connections {
        target: backendBridge

        function onConnectedChanged() {
            if (!backendBridge.connected) {
                stateLabel.text = "offline"
            }
        }

        function onMessageReceived(data) {
            if (data.type === "bot.message") {
                transcriptModel.append({ speaker: "BOT", text: data.payload.text })
            } else if (data.type === "game.state") {
                stateLabel.text = data.payload.phase
            } else if (data.type === "effect.trigger") {
                effectLabel.text = data.payload.effect + " " + data.payload.intensity
            } else if (data.type === "error") {
                transcriptModel.append({ speaker: "ERROR", text: data.payload.message })
            }
        }

        function onErrorOccurred(message) {
            transcriptModel.append({ speaker: "SYSTEM", text: message })
        }
    }

    Connections {
        target: cameraQrBridge

        function onQrDetected(value) {
            transcriptModel.append({ speaker: "QR", text: value })
            sendJson("qr.detected", { value: value })
        }
    }

    function sendJson(type, payload) {
        if (!backendBridge.connected) {
            transcriptModel.append({ speaker: "SYSTEM", text: "Backend neni pripojeny." })
            return
        }

        backendBridge.sendJson(type, payload)
    }

    ListModel {
        id: transcriptModel
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 18
        spacing: 12

        RowLayout {
            Layout.fillWidth: true

            Label {
                text: "Escape Bot"
                color: "#f1f4f8"
                font.pixelSize: 28
                font.bold: true
                Layout.fillWidth: true
            }

            Label {
                id: stateLabel
                text: "offline"
                color: "#85f0c2"
                font.pixelSize: 14
            }

            Label {
                id: effectLabel
                text: "no fx"
                color: "#f7b267"
                font.pixelSize: 14
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: "#171b22"
            border.color: "#2d3440"
            radius: 8

            ListView {
                anchors.fill: parent
                anchors.margins: 12
                spacing: 8
                model: transcriptModel

                delegate: Rectangle {
                    width: ListView.view.width
                    height: messageText.implicitHeight + 18
                    radius: 6
                    color: speaker === "BOT" ? "#202936" : "#1d232c"

                    Text {
                        id: messageText
                        anchors.fill: parent
                        anchors.margins: 9
                        color: "#edf2f7"
                        wrapMode: Text.WordWrap
                        text: "<b>" + speaker + ":</b> " + model.text
                    }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            TextField {
                id: input
                Layout.fillWidth: true
                placeholderText: "Popis prostoru, napoveda, nebo akce hrace..."
                color: "#f1f4f8"
                onAccepted: sendPlayerMessage()
            }

            Button {
                text: "Send"
                onClicked: sendPlayerMessage()
            }

            Button {
                text: "Debug QR"
                onClicked: cameraQrBridge.submitDebugQr("escapebot://clue/lobby-panel-a")
            }
        }
    }

    function sendPlayerMessage() {
        const text = input.text.trim()
        if (text.length === 0) {
            return
        }

        transcriptModel.append({ speaker: "PLAYER", text: text })
        sendJson("player.message", { text: text })
        input.clear()
    }
}
