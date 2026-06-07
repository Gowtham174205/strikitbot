package com.strikit.admin.network;

import android.content.Context;
import android.content.SharedPreferences;
import java.io.IOException;
import java.util.concurrent.TimeUnit;
import okhttp3.Interceptor;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;
import okhttp3.logging.HttpLoggingInterceptor;
import retrofit2.Retrofit;
import retrofit2.converter.gson.GsonConverterFactory;

public class ApiClient {
    private static Retrofit retrofit = null;
    private static ApiService apiService = null;
    private static final String PREFS_NAME = "strikit_prefs";
    private static final String KEY_SERVER_URL = "server_url";
    private static final String KEY_API_KEY = "api_key";
    
    // Default fallback values
    public static final String DEFAULT_URL = "https://bot.strikit.in/api/admin/"; // Production AWS server
    public static final String DEFAULT_KEY = "STRIKIT_ADMIN_SECRET";

    public static synchronized ApiService getApiService(Context context) {
        if (apiService == null) {
            initializeRetrofit(context);
        }
        return apiService;
    }

    public static synchronized void resetClient(Context context, String newUrl, String newApiKey) {
        SharedPreferences prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
        prefs.edit()
             .putString(KEY_SERVER_URL, newUrl)
             .putString(KEY_API_KEY, newApiKey)
             .apply();
        
        // Clear cached instances to force recreation on next call
        retrofit = null;
        apiService = null;
        initializeRetrofit(context);
    }

    public static String getServerUrl(Context context) {
        SharedPreferences prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
        return prefs.getString(KEY_SERVER_URL, DEFAULT_URL);
    }

    public static String getApiKey(Context context) {
        SharedPreferences prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
        return prefs.getString(KEY_API_KEY, DEFAULT_KEY);
    }

    private static void initializeRetrofit(Context context) {
        String baseUrl = getServerUrl(context);
        final String apiKey = getApiKey(context);

        // Add trailing slash to baseUrl if missing (required by Retrofit)
        if (!baseUrl.endsWith("/")) {
            baseUrl += "/";
        }

        HttpLoggingInterceptor logging = new HttpLoggingInterceptor();
        logging.setLevel(HttpLoggingInterceptor.Level.BODY);

        OkHttpClient client = new OkHttpClient.Builder()
                .connectTimeout(15, TimeUnit.SECONDS)
                .readTimeout(15, TimeUnit.SECONDS)
                .addInterceptor(logging)
                .addInterceptor(new Interceptor() {
                    @Override
                    public Response intercept(Chain chain) throws IOException {
                        Request original = chain.request();
                        Request.Builder requestBuilder = original.newBuilder()
                                .header("x-admin-key", apiKey)
                                .header("Content-Type", "application/json")
                                .method(original.method(), original.body());
                        Request request = requestBuilder.build();
                        return chain.proceed(request);
                    }
                })
                .build();

        try {
            retrofit = new Retrofit.Builder()
                    .baseUrl(baseUrl)
                    .addConverterFactory(GsonConverterFactory.create())
                    .client(client)
                    .build();

            apiService = retrofit.create(ApiService.class);
        } catch (Exception e) {
            e.printStackTrace();
        }
    }
}
