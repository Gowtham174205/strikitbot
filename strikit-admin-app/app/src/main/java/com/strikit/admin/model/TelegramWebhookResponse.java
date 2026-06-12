package com.strikit.admin.model;

public class TelegramWebhookResponse {
    private String message;
    private String registeredUrl;

    public String getMessage() { return message; }
    public void setMessage(String message) { this.message = message; }

    public String getRegisteredUrl() { return registeredUrl; }
    public void setRegisteredUrl(String registeredUrl) { this.registeredUrl = registeredUrl; }
}
