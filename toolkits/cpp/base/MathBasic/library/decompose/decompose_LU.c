#include <nmathbasic/nmathbasic.h>

void n_matrix_multiply_matrix(int m, int n, int o, double out[m][o], double A[m][n], double B[n][o])
{
    for (int i = 0; i < m; i++)
    {
        for (int j = 0; j < n; j++)
        {
            for (int k = 0; k < o; k++)
            {
                out[i][j] += A[i][k] * B[k][j];
            }
        }
    }
}

/**
 * http://rosettacode.org/wiki/LU_decomposition#C
 * https://courses.physics.illinois.edu/cs357/sp2020/notes/ref-9-linsys.html
 * Pivoting here means rearrange the A matrix so that we can easily reduce it later in 
 * the LU decomposition. 
 * Notice, A is unchanged, and P is changed, which records the row switching history
 */
void n_matrix_pivot(int n, double a[n][n], double p[n][n])
{
    for (int i = 0; i < n; i++)
    {
        for (int j = 0; j < n; j++)
        {
            p[i][j] = (i == j);
        }
    }

    for (int i = 0; i < n; i++)
    {
        int max_j = i;
        for (int j = i; j < n; j++)
        {
            if (fabs(a[j][i]) > fabs(a[max_j][i]))
            {
                max_j = j;
            }
        }
        if (max_j != i)
        {
            for (int k = 0; k < n; k++)
            {
                swap(p[i][k], p[max_j][k]);
            }
        }
    }
}

/**
 * http://rosettacode.org/wiki/LU_decomposition#C
 * First, find the pivot form of the matrix A
 * Then, 
 */
void matrix_LU_decompose(int n, double A[n][n], double L[n][n], double U[n][n], double P[n][n])
{
    n_matrix_pivot(n, A, P);
    double(*Aprime)[n][n];
    n_data_2D_double_init(n, n, &Aprime);
    n_matrix_multiply_matrix(n, n, n, *Aprime, P, A);
    for (int i = 0; i < n; i++)
    {
        L[i][i] = 1;
    }
    for (int i = 0; i < n; i++)
    {
        for (int j = 0; j < n; j++)
        {
            double s;
            if (j <= i)
            {
                s = 0;
                for (int k = 0; k < j; k++)
                {
                    s += L[j][k] * U[k][i];
                }
                U[j][i] = *Aprime[j][i] - s;
            }
            if (j >= i)
            {
                s = 0;
                for (int k = 0; k < i; k++)
                {
                    s += L[j][k] * U[k][i];
                }
                U[j][i] = (*Aprime[j][i] - s) / U[i][i];
            }
        }
    }
    free(Aprime);
}

void n_matrix_transpose(int m, int n, double out[n][m], double in[m][n])
{
    for (int i = 0; i < m; i++)
    {
        for (int j = 0; j < n; j++)
        {
            out[j][i] = in[i][j];
        }
    }
}

void n_matrix_duplicate(int m, int n, double out[m][n], double in[m][n])
{
    for (int i = 0; i < m; i++)
    {
        for (int j = 0; j < n; j++)
        {
            out[i][j] = in[i][j];
        }
    }
}

void n_matrix_minor(int m, int n, double out[m][n],double in[m][n], int d)
{
    n_matrix_duplicate(m,n,out,in);

    for (int i = 0; i < d; i++)
    {
        out[i][i] = 1;
    }

    for (int i = d; i < m; i++)
    {
        for (int j = d; j < n; j++)
        {
            out[i][j] = in[i][j];
        }
    }
}

void n_matrix_col(int m, int n, double *v, double in[m][n], int c){
    for (int i = 0; i < m; i++){
		v[i] = in[i][c];
    }
}

double n_vector_norm(int n, double *x){
    double sum = 0;
	for (int i = 0; i < n; i++){
        sum += x[i] * x[i];
    } 
	return sqrt(sum);
}
 
void n_matrix_QR_decompose_householder(int m, int n, double Q[m][m], double R[m][n], double M[m][n])
{
    // mat q[m->m];
	// mat z = m, z1;
    double **ptr;
    double *q[m];
    double(*z)[m][n];
    double(*z1)[m][n];
    n_data_2D_double_init(m, n, &z);
    n_data_2D_double_init(m, n, &z1);
    n_matrix_duplicate(m, n, *z, M);
    for (int k = 0; k < n && k < m - 1; k++)
    {
        double e[m], x[m], a;
        // z1 = n_matrix_minor(z, k);
		// if (z != m) matrix_delete(z);
		// z = z1;
        n_matrix_minor(m,n, z1, z, k);
        if (z != m) free(z);
        z=z1;

		// mcol(z, x, k);
        n_matrix_col(m,n,x,M,k);

		// a = vnorm(x, m->m);
        a = n_vector_norm(m,x);

		if (M[k][k] > 0) a = -a;

		for (int i = 0; i < m; i++){
			e[i] = (i == k) ? 1 : 0;
        }

		// vmadd(x, e, a, e, m->m);
        for (int i = 0; i < m; i++){
            e[i] = x[i] + a * e[i];
        }

        // vdiv(e, vnorm(e, m->m), e, m->m);
	    for (int i = 0; i < m; i++){
            e[i] = e[i] / n_vector_norm(m, e);
        } 

        // q[k] = vmul(e, m->m);
        n_data_2D_double_init(m, m, &q[k]);
        ptr = q[k];
        for (int i = 0; i < m; i++)
            for (int j = 0; j < m; j++)
                ptr[i][j] = -2 *  e[i] * e[j];
        for (int i = 0; i < m; i++)
            ptr[i][i] += 1;
 
		// z1 = matrix_mul(q[k], z);
		// if (z != m) matrix_delete(z);
		// z = z1;
        n_matrix_multiply_matrix(m, m, n, z1, q[k], z );
        if (z != m) free(z);
        z = z1;
    }
    free(z);
    n_matrix_duplicate(m, m, Q, q[0]);
    n_matrix_multiply_matrix(m, m, n, R, q[0], M );

	for (int i = 1; i < n && i < m - 1; i++) {
		// z1 = matrix_mul(q[i], Q);
        n_matrix_multiply_matrix(m, m, n, *z1, q[i], Q );

		if (i > 1) free(Q);
		Q=z1;
		free(q[i]);
	}
    n_matrix_multiply_matrix(m,m,n,*z,Q,M);
    R=z;
    n_matrix_transpose(m,m,q[0],Q);
    Q=q[0];
    

}

