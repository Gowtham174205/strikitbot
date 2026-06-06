package com.strikit.admin;

import android.content.DialogInterface;
import android.graphics.Color;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.Editable;
import android.text.TextWatcher;
import android.view.View;
import android.widget.EditText;
import android.widget.ImageButton;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;
import androidx.appcompat.app.AlertDialog;
import androidx.appcompat.app.AppCompatActivity;
import androidx.recyclerview.widget.LinearLayoutManager;
import androidx.recyclerview.widget.RecyclerView;
import com.strikit.admin.adapter.OwnerAdapter;
import com.strikit.admin.model.Owner;
import com.strikit.admin.network.ApiClient;
import com.strikit.admin.network.ApiService;
import java.util.ArrayList;
import java.util.List;
import retrofit2.Call;
import retrofit2.Callback;
import retrofit2.Response;

public class MainActivity extends AppCompatActivity implements OwnerAdapter.OnOwnerActionListener {

    private EditText etSearch;
    private ImageButton btnClearSearch;
    private RecyclerView rvOwners;
    private OwnerAdapter adapter;
    private ProgressBar loader;
    private TextView tvEmptyState;
    private ImageButton btnSettings;

    private ApiService apiService;
    private Handler searchHandler = new Handler(Looper.getMainLooper());
    private Runnable searchRunnable;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        // Bind Views
        etSearch = findViewById(R.id.etSearch);
        btnClearSearch = findViewById(R.id.btnClearSearch);
        rvOwners = findViewById(R.id.rvOwners);
        loader = findViewById(R.id.loader);
        tvEmptyState = findViewById(R.id.tvEmptyState);
        btnSettings = findViewById(R.id.btnSettings);

        // Set up RecyclerView
        rvOwners.setLayoutManager(new LinearLayoutManager(this));
        adapter = new OwnerAdapter(this, this);
        rvOwners.setAdapter(adapter);

        // Initialize API Service
        apiService = ApiClient.getApiService(this);

        // Fetch initial list
        fetchOwners("");

        // Setup Search Input Listener (Debounced search)
        etSearch.addTextChangedListener(new TextWatcher() {
            @Override
            public void beforeTextChanged(CharSequence s, int start, int count, int after) {}

            @Override
            public void onTextChanged(CharSequence s, int start, int before, int count) {
                if (s.length() > 0) {
                    btnClearSearch.setVisibility(View.VISIBLE);
                } else {
                    btnClearSearch.setVisibility(View.GONE);
                }

                // Debounce search by 500ms to avoid constant API requests
                searchHandler.removeCallbacks(searchRunnable);
                searchRunnable = () -> fetchOwners(s.toString().trim());
                searchHandler.postDelayed(searchRunnable, 500);
            }

            @Override
            public void afterTextChanged(Editable s) {}
        });

        // Clear Search Button
        btnClearSearch.setOnClickListener(v -> {
            etSearch.setText("");
            fetchOwners("");
        });

        // Settings Button
        btnSettings.setOnClickListener(v -> showSettingsDialog());
    }

    private void fetchOwners(String query) {
        loader.setVisibility(View.VISIBLE);
        tvEmptyState.setVisibility(View.GONE);

        apiService = ApiClient.getApiService(this);
        apiService.getOwners(query).enqueue(new Callback<List<Owner>>() {
            @Override
            public void onResponse(Call<List<Owner>> call, Response<List<Owner>> response) {
                loader.setVisibility(View.GONE);
                if (response.isSuccessful() && response.body() != null) {
                    List<Owner> list = response.body();
                    adapter.setOwners(list);
                    if (list.isEmpty()) {
                        tvEmptyState.setText("No owners found.");
                        tvEmptyState.setVisibility(View.VISIBLE);
                    } else {
                        tvEmptyState.setVisibility(View.GONE);
                    }
                } else {
                    adapter.setOwners(new ArrayList<>());
                    if (response.code() == 401) {
                        tvEmptyState.setText("Authentication failed (401 Unauthorized).\nCheck API Key in Settings.");
                    } else {
                        tvEmptyState.setText("Server error occurred (Code: " + response.code() + ").");
                    }
                    tvEmptyState.setVisibility(View.VISIBLE);
                    Toast.makeText(MainActivity.this, "Error fetching data: " + response.code(), Toast.LENGTH_SHORT).show();
                }
            }

            @Override
            public void onFailure(Call<List<Owner>> call, Throwable t) {
                loader.setVisibility(View.GONE);
                adapter.setOwners(new ArrayList<>());
                tvEmptyState.setText("Network error.\nPlease check your server connection and URL settings.");
                tvEmptyState.setVisibility(View.VISIBLE);
                Toast.makeText(MainActivity.this, "Network error: " + t.getMessage(), Toast.LENGTH_LONG).show();
            }
        });
    }

    @Override
    public void onApprove(Owner owner) {
        new AlertDialog.Builder(this)
                .setTitle("Approve Owner")
                .setMessage(getString(R.string.approve_confirm))
                .setPositiveButton("Approve", (dialog, which) -> {
                    loader.setVisibility(View.VISIBLE);
                    apiService.approveOwner(owner.getId()).enqueue(new Callback<Void>() {
                        @Override
                        public void onResponse(Call<Void> call, Response<Void> response) {
                            loader.setVisibility(View.GONE);
                            if (response.isSuccessful()) {
                                Toast.makeText(MainActivity.this, "Owner Approved Successfully!", Toast.LENGTH_SHORT).show();
                                fetchOwners(etSearch.getText().toString().trim());
                            } else {
                                Toast.makeText(MainActivity.this, "Failed to approve owner. Code: " + response.code(), Toast.LENGTH_LONG).show();
                            }
                        }

                        @Override
                        public void onFailure(Call<Void> call, Throwable t) {
                            loader.setVisibility(View.GONE);
                            Toast.makeText(MainActivity.this, "Network Error: " + t.getMessage(), Toast.LENGTH_LONG).show();
                        }
                    });
                })
                .setNegativeButton("Cancel", null)
                .show();
    }

    @Override
    public void onReject(Owner owner) {
        new AlertDialog.Builder(this)
                .setTitle("Deactivate Owner")
                .setMessage(getString(R.string.reject_confirm))
                .setPositiveButton("Deactivate", (dialog, which) -> {
                    loader.setVisibility(View.VISIBLE);
                    apiService.rejectOwner(owner.getId()).enqueue(new Callback<Void>() {
                        @Override
                        public void onResponse(Call<Void> call, Response<Void> response) {
                            loader.setVisibility(View.GONE);
                            if (response.isSuccessful()) {
                                Toast.makeText(MainActivity.this, "Owner Deactivated successfully.", Toast.LENGTH_SHORT).show();
                                fetchOwners(etSearch.getText().toString().trim());
                            } else {
                                Toast.makeText(MainActivity.this, "Failed to deactivate owner. Code: " + response.code(), Toast.LENGTH_LONG).show();
                            }
                        }

                        @Override
                        public void onFailure(Call<Void> call, Throwable t) {
                            loader.setVisibility(View.GONE);
                            Toast.makeText(MainActivity.this, "Network Error: " + t.getMessage(), Toast.LENGTH_LONG).show();
                        }
                    });
                })
                .setNegativeButton("Cancel", null)
                .show();
    }

    @Override
    public void onDelete(Owner owner) {
        new AlertDialog.Builder(this)
                .setTitle("DANGER: DELETE OWNER")
                .setMessage(getString(R.string.delete_confirm))
                .setPositiveButton("DELETE ALL", (dialog, which) -> {
                    loader.setVisibility(View.VISIBLE);
                    apiService.deleteOwner(owner.getId()).enqueue(new Callback<Void>() {
                        @Override
                        public void onResponse(Call<Void> call, Response<Void> response) {
                            loader.setVisibility(View.GONE);
                            if (response.isSuccessful()) {
                                Toast.makeText(MainActivity.this, "Owner and all cascading records deleted.", Toast.LENGTH_LONG).show();
                                fetchOwners(etSearch.getText().toString().trim());
                            } else {
                                Toast.makeText(MainActivity.this, "Failed to delete owner. Code: " + response.code(), Toast.LENGTH_LONG).show();
                            }
                        }

                        @Override
                        public void onFailure(Call<Void> call, Throwable t) {
                            loader.setVisibility(View.GONE);
                            Toast.makeText(MainActivity.this, "Network Error: " + t.getMessage(), Toast.LENGTH_LONG).show();
                        }
                    });
                })
                .setNegativeButton("Cancel", null)
                .setIcon(android.R.drawable.ic_dialog_alert)
                .show();
    }

    private void showSettingsDialog() {
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        int padding = (int) (20 * getResources().getDisplayMetrics().density);
        layout.setPadding(padding, padding, padding, padding);

        TextView tvUrlLabel = new TextView(this);
        tvUrlLabel.setText(getString(R.string.server_url_label));
        tvUrlLabel.setTextSize(14);
        tvUrlLabel.setTextColor(Color.WHITE);
        layout.addView(tvUrlLabel);

        final EditText etUrl = new EditText(this);
        etUrl.setHint("e.g. http://10.0.2.2:5000/api/admin/");
        etUrl.setText(ApiClient.getServerUrl(this));
        etUrl.setPadding(0, 16, 0, 16);
        layout.addView(etUrl);

        TextView tvKeyLabel = new TextView(this);
        tvKeyLabel.setText(getString(R.string.api_key_label));
        tvKeyLabel.setTextSize(14);
        tvKeyLabel.setTextColor(Color.WHITE);
        tvKeyLabel.setPadding(0, 24, 0, 0);
        layout.addView(tvKeyLabel);


        final EditText etKey = new EditText(this);
        etKey.setHint("e.g. STRIKIT_ADMIN_SECRET");
        etKey.setText(ApiClient.getApiKey(this));
        etKey.setPadding(0, 16, 0, 16);
        layout.addView(etKey);

        new AlertDialog.Builder(this)
                .setTitle(getString(R.string.settings_title))
                .setView(layout)
                .setPositiveButton(getString(R.string.save), (dialog, which) -> {
                    String url = etUrl.getText().toString().trim();
                    String key = etKey.getText().toString().trim();
                    
                    if (url.isEmpty()) {
                        Toast.makeText(MainActivity.this, "Server URL cannot be empty.", Toast.LENGTH_SHORT).show();
                        return;
                    }
                    
                    ApiClient.resetClient(MainActivity.this, url, key);
                    apiService = ApiClient.getApiService(MainActivity.this);
                    
                    Toast.makeText(MainActivity.this, "Settings Saved!", Toast.LENGTH_SHORT).show();
                    fetchOwners("");
                })
                .setNegativeButton(getString(R.string.cancel), null)
                .show();
    }
}
